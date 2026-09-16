"""Shared MediaWiki helpers for wiki-based sources.

Wikipedia and PsychonautWiki both run MediaWiki with the TextExtracts
extension, so title resolution and plain-text section extraction are the same
calls against a different api.php. This module holds that logic once; the
per-site source modules only carry the base URL and display name.
"""

from __future__ import annotations

import re
from typing import Any

import requests

from chemica import cache
from chemica.core import Section

# A descriptive UA identifying the app; Wikimedia's bot policy rejects the
# default python-requests User-Agent with a 403, and the same courtesy applies
# to other MediaWiki instances.
HEADERS = {"User-Agent": "chemica/0.1 (compound reference app; contact: cet)"}

# Matches MediaWiki section markers: == Heading ==, === Subheading ===, etc.
# The trailing newline is optional — an extract can end on the last marker.
_SECTION_RE = re.compile(r"\n(={2,4})\s*(.+?)\s*\1(?:\n|$)")

# Sections that are metadata, not article content — the same list the D app's
# isExcludedHeading filtered. 'See also' additionally feeds the cross-ref
# resolver (see section_links) before being dropped here.
_EXCLUDED_HEADINGS = {
    "references", "external links", "further reading", "see also", "notes",
    "bibliography", "sources", "footnotes", "gallery", "navigation",
}


# (api, query) → resolved title. fetch_profile + fetch_article resolve the same
# title through different source instances; memoizing here dedups the call.
# The extract/link caches below do the same for the heavier calls — page
# contents are stable within a session and the caches die with the process.
_TITLES: dict[tuple[str, str], str | None] = {}
_EXTRACTS: dict[tuple[str, str], list[Section]] = {}
_LINKS: dict[tuple[str, str, int], list[str]] = {}
_SECTION_LINKS: dict[tuple[str, str, str], list[str]] = {}


def resolve_title(api: str, query: str) -> str | None:
    """Resolve a search term to a canonical page title, or None if missing."""
    key = (api, query.lower())
    if key not in _TITLES:
        _TITLES[key] = _resolve_title(api, query)
    return _TITLES[key]


def _resolve_title(api: str, query: str) -> str | None:
    url = f"{api}?action=query&titles={requests.utils.quote(query)}&format=json&redirects=1"
    resp = cache.get(url, timeout=15, headers=HEADERS)
    if resp.status_code != 200:
        return None
    pages = resp.json().get("query", {}).get("pages", {})
    if not pages:
        return None
    page = next(iter(pages.values()))
    if "missing" in page:
        return None
    return page.get("title")


def extract_sections(api: str, title: str) -> list[Section]:
    """Fetch the full plain-text extract and split it into titled sections."""
    key = (api, title)
    if key not in _EXTRACTS:
        _EXTRACTS[key] = _extract_sections(api, title)
    return _EXTRACTS[key]


def _extract_sections(api: str, title: str) -> list[Section]:
    url = (
        f"{api}?action=query&prop=extracts&titles={requests.utils.quote(title)}"
        f"&format=json&explaintext=1&exsectionformat=wiki"
    )
    resp = cache.get(url, timeout=15, headers=HEADERS)
    if resp.status_code != 200:
        return []
    pages = resp.json().get("query", {}).get("pages", {})
    if not pages:
        return []
    page = next(iter(pages.values()))
    if "missing" in page:
        return []
    extract = page.get("extract", "")
    if not extract:
        return []
    return parse_sections(extract, title)


def page_links(api: str, title: str, limit: int = 50) -> list[str]:
    """Return the main-namespace page titles this article links to."""
    key = (api, title, limit)
    if key not in _LINKS:
        _LINKS[key] = _page_links(api, title, limit)
    return _LINKS[key]


def _page_links(api: str, title: str, limit: int) -> list[str]:
    url = (
        f"{api}?action=query&prop=links&titles={requests.utils.quote(title)}"
        f"&plnamespace=0&pllimit={limit}&format=json&formatversion=2"
    )
    resp = cache.get(url, timeout=15, headers=HEADERS)
    if resp.status_code != 200:
        return []
    pages = resp.json().get("query", {}).get("pages", [])
    if not pages:
        return []
    page = pages[0]
    if "missing" in page:
        return []
    links = page.get("links", [])
    return [link["title"] for link in links]


def section_links(api: str, title: str, heading: str) -> list[str]:
    """Main-namespace links inside a single named section.

    Two-step via action=parse: prop=sections finds the section index, then
    prop=links scoped to it. Lets the resolver use curated 'See also' links
    even though the section is filtered out of the displayed article.
    """
    key = (api, title, heading.lower())
    if key not in _SECTION_LINKS:
        _SECTION_LINKS[key] = _section_links(api, title, heading)
    return _SECTION_LINKS[key]


def _section_links(api: str, title: str, heading: str) -> list[str]:
    url = (
        f"{api}?action=parse&page={requests.utils.quote(title)}"
        f"&prop=sections&format=json&formatversion=2"
    )
    resp = cache.get(url, timeout=15, headers=HEADERS)
    if resp.status_code != 200:
        return []
    sections = resp.json().get("parse", {}).get("sections", [])
    index = next(
        (
            s["index"]
            for s in sections
            if s.get("line", "").strip().lower() == heading.lower()
        ),
        None,
    )
    if index is None:
        return []
    url = (
        f"{api}?action=parse&page={requests.utils.quote(title)}"
        f"&prop=links&section={index}&format=json&formatversion=2"
    )
    resp = cache.get(url, timeout=15, headers=HEADERS)
    if resp.status_code != 200:
        return []
    links = resp.json().get("parse", {}).get("links", [])
    return [link["title"] for link in links if link.get("ns") == 0]


def parse_sections(extract: str, title: str) -> list[Section]:
    """Split a plain-text extract into titled sections at == markers.

    The lead text before the first section marker becomes a level-1 section
    titled with the article name (matching the D app's behavior). Headings in
    _EXCLUDED_HEADINGS and their subsections are dropped.
    """
    sections: list[Section] = []
    matches = list(_SECTION_RE.finditer(extract))
    if not matches:
        # No section markers — the whole extract is the lead.
        if extract.strip():
            sections.append(Section(heading=title, level=1, text=extract.strip()))
        return sections

    # Lead section: everything before the first == marker.
    lead = extract[: matches[0].start()].strip()
    if lead:
        sections.append(Section(heading=title, level=1, text=lead))

    skip_below = 0  # nesting level of an excluded heading, 0 = not skipping
    for i, match in enumerate(matches):
        level = len(match.group(1))  # == is level 2, === is level 3
        heading = match.group(2).strip()
        if skip_below:
            if level > skip_below:
                continue
            skip_below = 0
        if heading.lower() in _EXCLUDED_HEADINGS:
            skip_below = level
            continue
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(extract)
        body = extract[body_start:body_end].strip()
        if heading:
            sections.append(Section(heading=heading, level=level, text=body))

    return sections
