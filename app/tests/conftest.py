"""pytest configuration — fixture replay, no network.

a owns the test suite; this conftest is the seam between the recorded fixtures
and the sources. When a source's fetch_* is called in a test, it reads from
tests/fixtures/ instead of hitting the live API.

The mechanism is a monkeypatch on each source's HTTP call, swapped to a function
that reads the matching fixture file. Tests opt in via the `recording` fixture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import pytest

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


class FixtureResponse:
    """Stand-in for requests.Response — just the bits the sources read.

    Holds the fixture file's raw text: .json() parses it for JSON endpoints,
    .text returns it for XML endpoints (PubMed efetch).
    """

    def __init__(self, text: str | None, status: int = 200):
        self._text = text or ""
        self.status_code = status

    def json(self) -> Any:
        return json.loads(self._text)

    @property
    def text(self) -> str:
        return self._text


@pytest.fixture
def recording(monkeypatch):
    """Replay recorded fixtures instead of hitting the network."""
    import requests

    # Sources route through chemica.cache.get; bypass the disk cache so
    # fixtures stay authoritative over anything a live run cached.
    monkeypatch.setenv("CHEMICA_NO_CACHE", "1")

    def fake_get(url: str, *args: Any, **kwargs: Any) -> FixtureResponse:
        if "/property/" in url and "pubchem" in url:
            cid = _extract_path_segment(url, "/compound/cid/", "/property")
            if "," in cid:
                return _batched_properties(cid)
        path = _fixture_for_url(url)
        if path is None or not path.exists():
            return FixtureResponse(None, status=404)
        return FixtureResponse(path.read_text(encoding="utf-8"))

    monkeypatch.setattr(requests, "get", fake_get)
    return fake_get


def _batched_properties(cid_list: str) -> FixtureResponse:
    """Merge per-CID property fixtures into one batched PropertyTable body."""
    rows = []
    for cid in cid_list.split(","):
        path = FIXTURE_DIR / "pubchem" / f"properties_{cid}.json"
        if not path.exists():
            continue
        rows.extend(json.loads(path.read_text(encoding="utf-8")).get("PropertyTable", {}).get("Properties", []))
    return FixtureResponse(json.dumps({"PropertyTable": {"Properties": rows}}))


def _fixture_for_url(url: str) -> Path | None:
    """Map a source URL to its recorded fixture file, name-aware.

    The query term (compound name or CID) is extracted from the URL so a
    not-found compound doesn't replay another compound's data.
    """
    if "pubchem.ncbi.nlm.nih.gov" in url:
        if "pug_view" in url:
            cid = _extract_path_segment(url, "/compound/", "/JSON")
            heading = _extract_query_param(url, "heading")
            if "Drug" in heading:
                return FIXTURE_DIR / "pubchem" / f"pugview_drug_{cid}.json"
            if "Pharmacology" in heading:
                return FIXTURE_DIR / "pubchem" / f"pugview_pharma_{cid}.json"
            return FIXTURE_DIR / "pubchem" / f"pugview_{cid}.json"
        if "/cids/JSON" in url:
            if "fastsimilarity" in url:
                cid = _extract_path_segment(url, "/fastsimilarity_2d/cid/", "/cids")
                return FIXTURE_DIR / "pubchem" / f"similar_{cid}.json"
            name = _extract_path_segment(url, "/compound/name/", "/cids")
            return FIXTURE_DIR / "pubchem" / f"cids_{name}.json"
        if "/property/" in url:
            cid = _extract_path_segment(url, "/compound/cid/", "/property")
            return FIXTURE_DIR / "pubchem" / f"properties_{cid}.json"
        if "/synonyms/JSON" in url:
            cid = _extract_path_segment(url, "/compound/cid/", "/synonyms")
            return FIXTURE_DIR / "pubchem" / f"synonyms_{cid}.json"
    if "en.wikipedia.org" in url:
        if "action=parse" in url:
            page = _safe_name(unquote(_extract_query_param(url, "page")))
            if "prop=sections" in url:
                return FIXTURE_DIR / "wikipedia" / f"parse_sections_{page}.json"
            section = _extract_query_param(url, "section")
            return FIXTURE_DIR / "wikipedia" / f"parse_links_{page}_{section}.json"
        if "/rest_v1/page/summary/" in url:
            title = url.split("/rest_v1/page/summary/", 1)[1]
            return FIXTURE_DIR / "wikipedia" / f"summary_{_safe_name(unquote(title))}.json"
        if "prop=extracts" in url:
            title = _extract_query_param(url, "titles")
            return FIXTURE_DIR / "wikipedia" / f"extracts_{_safe_name(unquote(title))}.json"
        if "prop=links" in url:
            title = _extract_query_param(url, "titles")
            return FIXTURE_DIR / "wikipedia" / f"links_{_safe_name(unquote(title))}.json"
        if "action=query" in url:
            title = _extract_query_param(url, "titles")
            return FIXTURE_DIR / "wikipedia" / f"query_{_safe_name(unquote(title))}.json"
    if "psychonautwiki.org" in url:
        if "action=parse" in url:
            # page=Template:SubstanceBox/{Title} for dose data; page={Title}
            # for the article wikitext (interactions).
            page = unquote(_extract_query_param(url, "page"))
            title = page.rsplit("/", 1)[-1]
            if page.startswith("Template:SubstanceBox"):
                return FIXTURE_DIR / "psychonaut" / f"substancebox_{_safe_name(title)}.json"
            return FIXTURE_DIR / "psychonaut" / f"wikitext_{_safe_name(title)}.json"
        if "prop=extracts" in url:
            title = _extract_query_param(url, "titles")
            return FIXTURE_DIR / "psychonaut" / f"extracts_{_safe_name(unquote(title))}.json"
        if "action=query" in url:
            title = _extract_query_param(url, "titles")
            return FIXTURE_DIR / "psychonaut" / f"query_{_safe_name(unquote(title))}.json"
    if "eutils.ncbi.nlm.nih.gov" in url:
        if "esearch" in url:
            term = _extract_query_param(url, "term")
            return FIXTURE_DIR / "pubmed" / f"esearch_{_safe_name(unquote(term))}.json"
        if "efetch" in url:
            ids = _extract_query_param(url, "id")
            return FIXTURE_DIR / "pubmed" / f"efetch_{ids}.xml"
    return None


def _extract_path_segment(url: str, prefix: str, suffix: str) -> str:
    start = url.find(prefix)
    if start == -1:
        return "unknown"
    start += len(prefix)
    end = url.find(suffix, start)
    if end == -1:
        end = len(url)
    return _safe_name(unquote(url[start:end]))


def _extract_query_param(url: str, param: str) -> str:
    from urllib.parse import parse_qs, urlsplit

    query = parse_qs(urlsplit(url).query)
    values = query.get(param, ["unknown"])
    return values[0]


def _safe_name(name: str) -> str:
    return name.replace(" ", "_").replace("/", "_")
