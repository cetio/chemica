"""PubMed source — fetch recent literature for a compound name.

Uses NCBI E-utilities: esearch resolves the term to PMIDs, efetch returns
the citation XML. Each paper becomes one article Section (heading = paper
title, text = abstract), so the Article slot in the page doubles as a
literature list.

Recorded fixtures (see tests/fixtures/) stand in for the live API in the
pytest suite so CI never depends on network reachability.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import requests

from chemica.core import Article, Compound, Section

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
HEADERS = {"User-Agent": "chemica/0.1 (compound reference app; contact: cet)"}

# NCBI asks callers to identify tool + contact on the query string.
ID_PARAMS = "tool=chemica&email=cet"
MAX_RESULTS = 5


class PubMedSource:
    name = "pubmed"

    def fetch_article(self, query: str) -> Article | None:
        pmids = self._search(query)
        if not pmids:
            return None
        sections = self._abstracts(pmids)
        if not sections:
            return None
        return Article(
            title=query,
            sections=sections,
            url=f"https://pubmed.ncbi.nlm.nih.gov/?term={requests.utils.quote(query)}",
            source="pubmed",
            raw={"pmids": pmids},
        )

    def fetch_compound(self, query: str) -> Compound | None:
        return None

    def _search(self, query: str) -> list[str]:
        url = (
            f"{EUTILS}/esearch.fcgi?db=pubmed&term={requests.utils.quote(query)}"
            f"&retmax={MAX_RESULTS}&retmode=json&{ID_PARAMS}"
        )
        resp = requests.get(url, timeout=15, headers=HEADERS)
        if resp.status_code != 200:
            return []
        return resp.json().get("esearchresult", {}).get("idlist", [])

    def _abstracts(self, pmids: list[str]) -> list[Section]:
        url = (
            f"{EUTILS}/efetch.fcgi?db=pubmed&id={','.join(pmids)}"
            f"&rettype=abstract&retmode=xml&{ID_PARAMS}"
        )
        resp = requests.get(url, timeout=15, headers=HEADERS)
        if resp.status_code != 200 or not resp.text:
            return []
        return _parse_articles(resp.text)


def _parse_articles(xml: str) -> list[Section]:
    """Turn PubMed citation XML into one Section per paper."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []

    sections: list[Section] = []
    for node in root.iter("PubmedArticle"):
        title_el = node.find(".//ArticleTitle")
        if title_el is None:
            continue
        heading = "".join(title_el.itertext()).strip()
        abstract = _abstract_text(node)
        if heading:
            sections.append(Section(heading=heading, level=2, text=abstract))
    return sections


def _abstract_text(node: ET.Element) -> str:
    """Join an article's AbstractText parts, keeping section labels."""
    parts: list[str] = []
    for el in node.findall(".//Abstract/AbstractText"):
        text = "".join(el.itertext()).strip()
        label = el.get("Label")
        if label:
            text = f"{label}: {text}"
        if text:
            parts.append(text)
    return "\n\n".join(parts)
