"""Wikipedia source — fetch an article by compound name.

Uses the MediaWiki REST API. The first increment maps a name to titled sections
of readable text; the blend path is out of scope.

Recorded fixtures (see tests/fixtures/) stand in for the live API in the pytest
suite so CI never depends on network reachability.
"""

from __future__ import annotations

from typing import Any

import requests

from chemica.core import Article, Compound, Section

REST = "https://en.wikipedia.org/api/rest_v1"
API = "https://en.wikipedia.org/w/api.php"

# Wikimedia's bot policy rejects the default python-requests User-Agent with a
# 403. A descriptive UA identifying the app and a contact fixes it.
HEADERS = {"User-Agent": "chemica/0.1 (compound reference app; contact: cet)"}


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
        summary_url = f"{REST}/page/summary/{requests.utils.quote(title)}"
        summary = requests.get(summary_url, timeout=15, headers=HEADERS)
        lead_text = ""
        if summary.status_code == 200:
            lead_text = summary.json().get("extract", "")
        sections: list[Section] = []
        if lead_text:
            sections.append(Section(heading=title, level=1, text=lead_text))
        # Full section breakdown via the mobile-sections endpoint is the next
        # step; the lead extract is enough for "aspirin in, article out".
        return sections
