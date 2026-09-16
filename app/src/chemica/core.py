"""Core data model and fetch interface.

The two entry points the front-ends call:

    fetch_compound(name) -> Compound
    fetch_article(name)  -> Article

Both are standalone-importable — no web/desktop coupling. The desktop app hangs
off the same seam the web shell does.

Sources are pluggable behind a Source protocol so the first increment ships
PubChem + Wikipedia and the rest (PsychonautWiki, PubMed/PMC) plug in later
without touching the front-ends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class Compound:
    """A PubChem compound record — the property infobox + identifiers."""

    name: str
    cid: int | None = None
    formula: str | None = None
    molecular_weight: float | None = None
    mass: float | None = None
    charge: int | None = None
    tpsa: float | None = None
    xlogp: float | None = None
    smiles: str | None = None
    inchi: str | None = None
    inchikey: str | None = None
    cas: str | None = None
    synonyms: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Article:
    """A sourced article shaped into titled sections — the readable page."""

    title: str
    sections: list["Section"]
    url: str | None = None
    source: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Section:
    heading: str
    level: int
    text: str


@dataclass(frozen=True)
class CrossReference:
    """A compound mentioned in an article, resolved to a real compound."""

    name: str
    compound: Compound



@dataclass(frozen=True)
class DoseLadder:
    """One route's dose ladder (threshold → heavy), as printed by the source.

    Values keep the source's units in the string ("50 - 150 mg") — the panel
    displays what the wiki says rather than trusting a unit parse.
    """

    route: str
    threshold: str | None = None
    light: str | None = None
    common: str | None = None
    strong: str | None = None
    heavy: str | None = None
    bioavailability: str | None = None


@dataclass(frozen=True)
class EffectsProfile:
    """One route's experience timeline (onset → aftereffects)."""

    route: str
    onset: str | None = None
    comeup: str | None = None
    peak: str | None = None
    offset: str | None = None
    total: str | None = None
    aftereffects: str | None = None


@dataclass(frozen=True)
class CompoundPage:
    """Everything the front-ends need to render one compound page.

    Sources contribute what they cover: PubChem the compound, Wikipedia and
    PsychonautWiki articles, PubMed literature, PsychonautWiki the dose
    ladders and timelines. Cross-references are resolved from the article text.
    Absent coverage stays absent — an empty list means "no source had this",
    not "this compound has none".
    """

    compound: Compound | None
    articles: list[Article]
    dose_ladders: list[DoseLadder]
    effects: list[EffectsProfile]
    cross_references: list[CrossReference] = field(default_factory=list)


@runtime_checkable
class Source(Protocol):
    """A fetcher the core can blend. First increment ships two of these."""

    name: str

    def fetch_compound(self, query: str) -> Compound | None: ...

    def fetch_article(self, query: str) -> Article | None: ...


def fetch_compound(name: str) -> Compound | None:
    """Resolve a name to a Compound via the registered sources.

    First increment: PubChem only. Returns None if no source has the compound.
    """
    from chemica.sources.pubchem import PubChemSource

    return PubChemSource().fetch_compound(name)


def fetch_article(name: str) -> Article | None:
    """Resolve a name to the first sourced Article, or None if none has one.

    Sources answer in priority order (Wikipedia, PsychonautWiki, PubMed); the
    first hit wins. The multi-source view is fetch_compound_page.
    """
    return next(iter(_article_sources(name)), None)


def fetch_compound_page(name: str) -> CompoundPage:
    """Compose the full page: compound, every sourced article, dose data."""
    from chemica.crossrefs import find_cross_references, resolve_candidates
    from chemica.sources.mediawiki import page_links as wiki_links
    from chemica.sources.psychonaut import PsychonautWikiSource
    from chemica.sources.pubchem import PubChemSource
    from chemica.sources.wikipedia import API as WIKI_API

    pw = PsychonautWikiSource()
    ladders, effects = pw.fetch_profile(name)
    articles = list(_article_sources(name))
    compound = PubChemSource().fetch_compound(name)

    def resolver(query: str) -> Compound | None:
        if query.lower() == name.lower():
            return None
        try:
            return fetch_compound(query)
        except Exception:
            return None

    article_text = "\n".join(
        section.text for article in articles for section in article.sections
    )
    text_candidates = find_cross_references(article_text, resolver)

    wiki_article = next(
        (a for a in articles if a.source == "wikipedia"), None
    )
    link_candidates: set[str] = set()
    if wiki_article:
        raw_titles = wiki_links(WIKI_API, wiki_article.title)
        # A link is a real mention only if it appears in the article text,
        # filtering out navbox/template-only links (e.g. the Stimulants box).
        text_lower = article_text.lower()
        link_candidates = {
            title.split("(")[0].strip()
            for title in raw_titles
            if title.split("(")[0].strip().lower() in text_lower
        }
    link_refs = resolve_candidates(link_candidates, resolver)

    # Merge, preferring link-based references and keeping names stable.
    by_cid: dict[int, CrossReference] = {}
    for ref in text_candidates + link_refs:
        if ref.compound.cid is not None and ref.compound.cid not in by_cid:
            by_cid[ref.compound.cid] = ref
    cross_references = list(by_cid.values())[:12]

    return CompoundPage(
        compound=compound,
        articles=articles,
        dose_ladders=ladders,
        effects=effects,
        cross_references=cross_references,
    )


def _article_sources(name: str):
    """Yield each registered source's Article for the name, skipping declines."""
    from chemica.sources.psychonaut import PsychonautWikiSource
    from chemica.sources.pubmed import PubMedSource
    from chemica.sources.wikipedia import WikipediaSource

    for source in (WikipediaSource(), PsychonautWikiSource(), PubMedSource()):
        article = source.fetch_article(name)
        if article is not None:
            yield article
