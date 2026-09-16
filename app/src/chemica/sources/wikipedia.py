"""Wikipedia source — fetch an article by compound name.

Uses the MediaWiki API to get the full plain-text extract with section markers.
The first increment mapped a name to the lead extract only; this version returns
the full section breakdown (history, uses, side effects, etc.).

Recorded fixtures (see tests/fixtures/) stand in for the live API in the pytest
suite so CI never depends on network reachability.
"""

from __future__ import annotations

import re
from typing import Any

import requests

from chemica.core import Article, Compound, Section

REST = "https://en.wikipedia.org/api/rest_v1"
API = "https://en.wikipedia.org/w/api.php"

# Wikimedia's bot policy rejects the default python-requests User-Agent with a
# 403. A descriptive UA identifying the app and a contact fixes it.
HEADERS = {"User-Agent": "chemica/0.1 (compound reference app; contact: cet)"}

# Matches MediaWiki section markers: == Heading ==, === Subheading ===, etc.
_SECTION_RE = re.compile(r"\n(={2,4})\s*(.+?)\s*\1\n")


class WikipediaSource:
    name = "wikipedia"

    def fetch_article(self, query: str) -> Article | None:
        title = self._resolve_title(query)
        if title is None:
            return None
        sections = self._sections(title)
        if not sections:
            return None
        return Article(
            title=title,
            sections=sections,
            url=f"https://en.wikipedia.org/wiki/{requests.utils.quote(title)}",
            source="wikipedia",
            raw={"title": title},
        )

    def fetch_compound(self, query: str) -> Compound | None:
        return None

    def _resolve_title(self, query: str) -> str | None:
        url = f"{API}?action=query&titles={requests.utils.quote(query)}&format=json&redirects=1"
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

    def _sections(self, title: str) -> list[Section]:
        # The extracts API returns the full plain-text article with == Heading ==
        # style section markers. explaintext=1 gives plain text, exsectionformat=wiki
        # preserves the == markers so we can parse them.
        url = (
            f"{API}?action=query&prop=extracts&titles={requests.utils.quote(title)}"
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
        return _parse_sections(extract, title)


def _parse_sections(extract: str, title: str) -> list[Section]:
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
