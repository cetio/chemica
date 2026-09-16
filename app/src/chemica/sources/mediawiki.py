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

from chemica.core import Section

# A descriptive UA identifying the app; Wikimedia's bot policy rejects the
# default python-requests User-Agent with a 403, and the same courtesy applies
# to other MediaWiki instances.
HEADERS = {"User-Agent": "chemica/0.1 (compound reference app; contact: cet)"}

# Matches MediaWiki section markers: == Heading ==, === Subheading ===, etc.
_SECTION_RE = re.compile(r"\n(={2,4})\s*(.+?)\s*\1\n")


def resolve_title(api: str, query: str) -> str | None:
    """Resolve a search term to a canonical page title, or None if missing."""
    url = f"{api}?action=query&titles={requests.utils.quote(query)}&format=json&redirects=1"
    resp = requests.get(url, timeout=15, headers=HEADERS)
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
    url = (
        f"{api}?action=query&prop=extracts&titles={requests.utils.quote(title)}"
        f"&format=json&explaintext=1&exsectionformat=wiki"
    )
    resp = requests.get(url, timeout=15, headers=HEADERS)
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


def parse_sections(extract: str, title: str) -> list[Section]:
    """Split a plain-text extract into titled sections at == markers.

    The lead text before the first section marker becomes a level-1 section
    titled with the article name (matching the D app's behavior).
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

    for i, match in enumerate(matches):
        level = len(match.group(1))  # == is level 2, === is level 3
        heading = match.group(2).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(extract)
        body = extract[body_start:body_end].strip()
        if heading:
            sections.append(Section(heading=heading, level=level, text=body))

    return sections
