"""Tests for chemica.core — the contract the web and desktop shells hang off.

Recorded fixtures (tests/fixtures/) replay real API responses captured from
PubChem and Wikipedia on 2026-09-15; the suite never touches the network.
Assertions pin the shape "aspirin in, sourced article out" needs: compound
identifiers + properties, article title + ordered sections.
"""

from __future__ import annotations

from typing import Any

import pytest
import requests

from chemica import Article, Compound, fetch_article, fetch_compound
from chemica.core import Section, Source
from chemica.sources.pubchem import PubChemSource
from chemica.sources.wikipedia import WikipediaSource

# Values recorded from the live APIs for aspirin.
ASPIRIN_CID = 2244
ASPIRIN_SMILES = "CC(=O)OC1=CC=CC=C1C(=O)O"
ASPIRIN_INCHIKEY = "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
ASPIRIN_CAS = "50-78-2"


class _StubResponse:
    """Minimal requests.Response stand-in for negative-path tests."""

    def __init__(self, payload: Any = None, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        return self._payload


def test_fetch_compound_aspirin(recording):
    compound = fetch_compound("aspirin")

    assert isinstance(compound, Compound)
    assert compound.name == "aspirin"
    assert compound.cid == ASPIRIN_CID
    assert compound.formula == "C9H8O4"
    assert compound.molecular_weight == pytest.approx(180.16)
    assert compound.mass == pytest.approx(180.04225873)
    assert compound.charge == 0
    assert compound.tpsa == pytest.approx(63.6)
    assert compound.xlogp == pytest.approx(1.2)
    assert compound.smiles == ASPIRIN_SMILES
    assert compound.inchi is not None and compound.inchi.startswith("InChI=1S/C9H8O4")
    assert compound.inchikey == ASPIRIN_INCHIKEY
    assert "aspirin" in compound.synonyms
    assert "ACETYLSALICYLIC ACID" in compound.synonyms
    assert compound.raw


def test_compound_cas_is_deferred_but_present_in_synonyms(recording):
    # PubChem puts the CAS RN in the synonyms payload; extraction into
    # Compound.cas is deferred. Pin both facts so landing it flips this test
    # instead of drifting silently.
    compound = fetch_compound("aspirin")
    assert compound is not None
    assert compound.cas is None
    assert ASPIRIN_CAS in compound.synonyms


def test_fetch_compound_unknown_returns_none(monkeypatch):
    def not_found(*args: Any, **kwargs: Any) -> _StubResponse:
        return _StubResponse(status_code=404)

    monkeypatch.setattr(requests, "get", not_found)
    assert fetch_compound("zzz-not-a-compound-zzz") is None


def test_fetch_article_aspirin(recording):
    article = fetch_article("aspirin")

    assert isinstance(article, Article)
    assert article.title == "Aspirin"
    assert article.url == "https://en.wikipedia.org/wiki/Aspirin"
    assert article.sections
    lead = article.sections[0]
    assert isinstance(lead, Section)
    assert lead.heading == "Aspirin"
    assert lead.level == 1
    assert "acetylsalicylic acid" in lead.text


def test_fetch_article_missing_returns_none(monkeypatch):
    def missing_page(url: str, *args: Any, **kwargs: Any) -> _StubResponse:
        if "action=query" in url:
            return _StubResponse({"query": {"pages": {"-1": {"missing": ""}}}})
        return _StubResponse(status_code=404)

    monkeypatch.setattr(requests, "get", missing_page)
    assert fetch_article("zzz-not-a-compound-zzz") is None


def test_sources_satisfy_source_protocol():
    assert isinstance(PubChemSource(), Source)
    assert isinstance(WikipediaSource(), Source)


def test_sources_decline_what_they_do_not_own():
    # Each source answers for what it owns; blend sources plug in behind the
    # same seam later.
    assert PubChemSource().fetch_article("aspirin") is None
    assert WikipediaSource().fetch_compound("aspirin") is None


def test_models_are_immutable(recording):
    compound = fetch_compound("aspirin")
    assert compound is not None
    with pytest.raises(AttributeError):
        compound.cid = 0
