"""PubMed source — fetch recent literature for a compound name.

Uses NCBI E-utilities: esearch resolves the term to PMIDs, efetch returns
the citation XML. The data surfaces two ways: an Article (one Section per
paper, heading = title, text = abstract) and References (one per paper,
title + pubmed.ncbi.nlm.nih.gov/{pmid}/ link) for the page's references panel.

Recorded fixtures (see tests/fixtures/) stand in for the live API in the
pytest suite so CI never depends on network reachability.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import requests

from chemica import cache
from chemica.core import Article, Compound, Reference, Section

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
HEADERS = {"User-Agent": "chemica/0.1 (compound reference app; contact: cet)"}
PUBMED_URL = "https://pubmed.ncbi.nlm.nih.gov"

# NCBI asks callers to identify tool + contact on the query string.
ID_PARAMS = "tool=chemica&email=cet"
MAX_RESULTS = 5


class PubMedSource:
    name = "pubmed"

    def fetch_article(self, query: str) -> Article | None:
        papers = self._papers(query)
        if not papers:
            return None
        sections = [Section(heading=title, level=2, text=abstract) for _pmid, title, abstract in papers]
        return Article(
            title=query,
            sections=sections,
            url=f"{PUBMED_URL}/?term={requests.utils.quote(query)}",
            source="pubmed",
            raw={"pmids": [pmid for pmid, _t, _a in papers]},
        )

    def fetch_references(self, query: str) -> list[Reference]:
        """One Reference per paper — title links to the PubMed record."""
        return [
            Reference(
                title=title,
                url=f"{PUBMED_URL}/{pmid}/",
                source="pubmed",
                snippet=abstract or None,
            )
            for pmid, title, abstract in self._papers(query)
        ]

    def fetch_compound(self, query: str) -> Compound | None:
        return None

    def _papers(self, query: str) -> list[tuple[str, str, str]]:
        """(pmid, title, abstract) tuples for the search term."""
        pmids = self._search(query)
        if not pmids:
            return []
        return _parse_articles(self._efetch(pmids))

    def _search(self, query: str) -> list[str]:
        # Exact phrase in title/abstract first: PubMed's term mapping expands
        # acronyms like 'MMC' into unrelated fields (battery/steel papers on
        # the 2-MMC sweep). If the phrase finds nothing, the query is too
        # exotic for exact matching (α-PVP is indexed as alpha-PVP) and the
        # plain term gets a chance instead.
        pmids = self._esearch(f'"{query}"[Title/Abstract]')
        return pmids or self._esearch(query)

    def _esearch(self, term: str) -> list[str]:
        url = (
            f"{EUTILS}/esearch.fcgi?db=pubmed&term={requests.utils.quote(term)}"
            f"&retmax={MAX_RESULTS}&retmode=json&{ID_PARAMS}"
        )
        resp = cache.get(url, timeout=15, headers=HEADERS)
        if resp.status_code != 200:
            return []
        return resp.json().get("esearchresult", {}).get("idlist", [])

    def _efetch(self, pmids: list[str]) -> str:
        url = f"{EUTILS}/efetch.fcgi?db=pubmed&id={','.join(pmids)}&rettype=abstract&retmode=xml&{ID_PARAMS}"
        resp = cache.get(url, timeout=15, headers=HEADERS)
        if resp.status_code != 200:
            return ""
        return resp.text


def _parse_articles(xml: str) -> list[tuple[str, str, str]]:
    """Turn PubMed citation XML into (pmid, title, abstract) tuples."""
    if not xml:
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []

    papers: list[tuple[str, str, str]] = []
    for node in root.iter("PubmedArticle"):
        pmid_el = node.find(".//PMID")
        title_el = node.find(".//ArticleTitle")
        if pmid_el is None or title_el is None:
            continue
        title = "".join(title_el.itertext()).strip()
        if title:
            papers.append((pmid_el.text or "", title, _abstract_text(node)))
    return papers


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
