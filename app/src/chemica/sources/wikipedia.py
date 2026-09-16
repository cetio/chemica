"""Wikipedia source — fetch an article by compound name.

Wikipedia runs MediaWiki with the TextExtracts extension; all the fetch
mechanics (title resolution, extract, section splitting, link listing) live in
chemica.sources.mediawiki — this module only carries the site identity.

Recorded fixtures (see tests/fixtures/) stand in for the live API in the pytest
suite so CI never depends on network reachability.
"""

from __future__ import annotations

import requests

from chemica.core import Article, Compound
from chemica.sources import mediawiki

API = "https://en.wikipedia.org/w/api.php"
SITE = "https://en.wikipedia.org/wiki"


class WikipediaSource:
    name = "wikipedia"

    def fetch_article(self, query: str) -> Article | None:
        title = mediawiki.resolve_title(API, query)
        if title is None:
            return None
        sections = mediawiki.extract_sections(API, title)
        if not sections:
            return None
        return Article(
            title=title,
            sections=sections,
            url=f"{SITE}/{requests.utils.quote(title)}",
            source="wikipedia",
            raw={"title": title},
        )

    def fetch_compound(self, query: str) -> Compound | None:
        return None
