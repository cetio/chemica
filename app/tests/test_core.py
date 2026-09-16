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

from chemica import (
    Article,
    Compound,
    CompoundPage,
    fetch_article,
    fetch_compound,
    fetch_compound_page,
)
from chemica.core import DoseLadder, EffectsProfile, Reference, Section, Source
from chemica.sources.psychonaut import PsychonautWikiSource
from chemica.sources.pubchem import PubChemSource
from chemica.sources.pubmed import PubMedSource
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
    assert compound.name == "Aspirin"  # first letter cased for display
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
    # PubChem puts the CAS RN in the synonyms payload; _cas() extracts it
    # from the same call so Compound.cas is populated without an extra request.
    compound = fetch_compound("aspirin")
    assert compound is not None
    assert compound.cas == ASPIRIN_CAS
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
    assert isinstance(PsychonautWikiSource(), Source)
    assert isinstance(PubMedSource(), Source)


def test_sources_decline_what_they_do_not_own():
    # Each source answers for what it owns; blend sources plug in behind the
    # same seam later.
    assert PubChemSource().fetch_article("aspirin") is None
    assert WikipediaSource().fetch_compound("aspirin") is None
    assert PsychonautWikiSource().fetch_compound("caffeine") is None
    assert PubMedSource().fetch_compound("aspirin") is None


def test_psychonautwiki_article_caffeine(recording):
    # PsychonautWiki covers recreational substances; caffeine is the demo
    # compound that exercises every lane.
    article = PsychonautWikiSource().fetch_article("caffeine")

    assert isinstance(article, Article)
    assert article.title == "Caffeine"
    assert article.source == "psychonautwiki"
    assert article.url == "https://psychonautwiki.org/wiki/Caffeine"
    assert article.sections[0].heading == "Caffeine"
    assert len(article.sections) > 5


def test_psychonautwiki_profile_caffeine(recording):
    # Recorded SubstanceBox wikitext for Caffeine: oral ladder 25 mg threshold
    # through "500 mg +" heavy, plus a full duration timeline.
    ladders, effects = PsychonautWikiSource().fetch_profile("caffeine")

    oral = next(lad for lad in ladders if lad.route == "Oral")
    assert isinstance(oral, DoseLadder)
    assert oral.threshold == "25 mg"
    assert oral.common == "50 - 150 mg"
    assert oral.heavy == "500 mg +"
    assert oral.bioavailability == "~100%"

    oral_fx = next(e for e in effects if e.route == "Oral")
    assert isinstance(oral_fx, EffectsProfile)
    assert oral_fx.onset == "5 - 10 minutes"
    assert oral_fx.total == "2 - 5 hours"
    assert oral_fx.aftereffects == "3 - 6 hours"


def test_psychonautwiki_declines_aspirin(recording):
    # Recorded live: PsychonautWiki's query for aspirin returns a missing page.
    # The source declines rather than serving a search-results page.
    assert PsychonautWikiSource().fetch_article("aspirin") is None
    assert PsychonautWikiSource().fetch_profile("aspirin") == ([], [])


def test_pubmed_article_aspirin(recording):
    # Recorded esearch/efetch for aspirin: five recent papers, each a section.
    article = PubMedSource().fetch_article("aspirin")

    assert isinstance(article, Article)
    assert article.source == "pubmed"
    assert article.url == "https://pubmed.ncbi.nlm.nih.gov/?term=aspirin"
    assert len(article.sections) == 5
    for paper in article.sections:
        assert paper.heading  # paper title
        assert paper.text  # abstract


def test_pubmed_references_aspirin(recording):
    # The references panel needs per-paper links, not one article-level URL.
    references = PubMedSource().fetch_references("aspirin")

    assert len(references) == 5
    for ref in references:
        assert isinstance(ref, Reference)
        assert ref.source == "pubmed"
        assert ref.title
        assert ref.url and ref.url.startswith("https://pubmed.ncbi.nlm.nih.gov/")
        assert ref.url.rstrip("/").rsplit("/", 1)[-1].isdigit()  # PMID link


def test_fetch_article_stays_first_hit(recording):
    # The web shell's contract: one article, first source that answers.
    article = fetch_article("aspirin")
    assert article is not None
    assert article.title == "Aspirin"
    assert article.url.startswith("https://en.wikipedia.org/")


def test_fetch_compound_page_caffeine(recording):
    # The composer the front-ends will bind to: compound + all articles +
    # dose data in one call. Caffeine exercises every lane.
    page = fetch_compound_page("caffeine")

    assert isinstance(page, CompoundPage)
    assert page.compound is not None
    assert page.compound.cid == 2519
    assert page.compound.formula == "C8H10N4O2"

    by_source = {a.source: a for a in page.articles}
    # PubMed is no longer an article source — it contributes only via
    # page.references. The PubMed Article was dead weight: never the main
    # article (wikipedia/PW win) and only fed cross-ref noise.
    assert set(by_source) == {"wikipedia", "psychonautwiki"}
    assert by_source["wikipedia"].title == "Caffeine"
    assert by_source["psychonautwiki"].sections

    routes = {lad.route for lad in page.dose_ladders}
    assert "Oral" in routes
    assert {e.route for e in page.effects} >= {"Oral"}

    assert len(page.references) == 5
    assert all(r.source == "pubmed" for r in page.references)
    assert page.cross_references is not None
    # 'See also' is filtered from the article body but its curated links feed
    # the resolver — Methylliberine is past the first-50 outlinks, so it only
    # reaches cross_references through that path.
    xref_cids = {r.compound.cid for r in page.cross_references}
    assert 15872156 in xref_cids  # Methylliberine


def test_fetch_interactions_ketamine(recording):
    # Recorded PW article wikitext: 'Dangerous interactions' lines with
    # [[DangerousInteraction::X]] / [[UncertainInteraction::X]] annotations;
    # a bullet naming two substances shares one description.
    from chemica.core import fetch_interactions

    interactions = fetch_interactions("ketamine")
    by_substance = {i.substance: i for i in interactions}
    assert by_substance["Alcohol"].severity == "dangerous"
    assert "vomit aspiration" in by_substance["Alcohol"].description
    assert by_substance["GHB"].severity == "dangerous"
    assert by_substance["GBL"].description == by_substance["GHB"].description
    assert by_substance["Amphetamines"].severity == "uncertain"


def test_fetch_classes_ketamine(recording):
    # The recorded PW wikitext carries [[Chemical class::…]] and
    # [[Psychoactive class::…]] annotations in the lead.
    from chemica.core import fetch_classes

    classes = fetch_classes("ketamine")
    assert classes is not None
    assert classes.chemical == "arylcyclohexylamine"
    assert classes.psychoactive == "dissociative"


def test_fetch_subjective_ketamine(recording):
    # Recorded PW wikitext annotates addiction potential, tolerance spans,
    # and inline [[Effect::X]] tags through the article body.
    from chemica.sources.psychonaut import PsychonautWikiSource

    profile = PsychonautWikiSource().fetch_subjective("ketamine")
    assert profile is not None
    assert "abuse potential" in profile.addiction_potential
    assert profile.tolerance_half == "14 days"
    assert profile.tolerance_zero == "28 days"
    assert "Sedation" in profile.effect_tags
    assert len(profile.effect_tags) == len(set(profile.effect_tags))


def test_fetch_drug_profile_ketamine(recording):
    # Recorded PUG-View 'Drug and Medication Information': regulatory fields
    # for a real drug record — ketamine is Approved + Prescription Only.
    from chemica.core import fetch_drug_profile

    profile = fetch_drug_profile("ketamine")
    assert profile is not None
    assert profile.max_phase == "Approved"
    assert profile.availability == "Prescription Only"
    assert "Parenteral" in profile.routes
    assert any("Dissociative" in c for c in profile.drug_classes)
    assert profile.half_life


def test_fetch_hazards_caffeine(recording):
    # PUG-View GHS Classification: pictograms dedupe across notifiers,
    # strictest signal wins, statements keep their notifier %.
    from chemica.core import fetch_hazards

    hazards = fetch_hazards("caffeine")
    assert hazards is not None
    assert hazards.signal == "Danger"
    assert "GHS07" in hazards.pictograms
    assert any(s.startswith("H302") for s in hazards.statements)


def test_parse_sections_filters_tail_headings():
    # Meta sections (See also, Notes, References, ...) are not article content
    # — the D app filtered the same list. An excluded heading's subsections go
    # with it; real sections after it still render.
    from chemica.sources.mediawiki import parse_sections

    extract = (
        "Lead paragraph.\n"
        "== Uses ==\nReal content.\n"
        "== See also ==\n* Theobromine\n"
        "=== Curated sub ===\nmore junk\n"
        "== Notes ==\nnote text\n"
        "== Pharmacology ==\nReal pharmacology.\n"
    )
    sections = parse_sections(extract, "X")
    assert [s.heading for s in sections] == ["X", "Uses", "Pharmacology"]


def test_models_are_immutable(recording):
    compound = fetch_compound("aspirin")
    assert compound is not None
    with pytest.raises(AttributeError):
        compound.cid = 0
