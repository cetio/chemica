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
    # Set when the query resolved to a salt record and we fell through to the
    # freebase — carries the salt's PubChem title ("Phenmetrazine hydrochloride").
    salt_form: str | None = None
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
class Reference:
    """One literature citation (PubMed paper): title + link + abstract snippet."""

    title: str
    url: str | None = None
    source: str | None = None
    snippet: str | None = None



@dataclass(frozen=True)
class HazardProfile:
    """GHS hazard data for the compound — pictograms, signal, H-statements."""

    pictograms: list[str] = field(default_factory=list)  # e.g. "GHS07"
    signal: str | None = None  # "Warning" or "Danger"
    statements: list[str] = field(default_factory=list)  # "H302: Harmful if swallowed"
    source: str | None = "pubchem"


@dataclass(frozen=True)
class Interaction:
    """A substance interaction line from PsychonautWiki's annotated markup.

    Severity comes straight from the [[*Interaction::…]] semantic tag —
    'dangerous' | 'unsafe' | 'uncertain'. One line can name several
    substances that share a description (GHB / GBL), so each gets its own
    Interaction with the same text.
    """

    substance: str
    severity: str
    description: str | None = None


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
    references: list[Reference] = field(default_factory=list)
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


def fetch_compound_page(name: str, defer: frozenset[str] = frozenset()) -> CompoundPage:
    """Compose the full page: compound, every sourced article, dose data.

    `defer` names the expensive fields to skip on the first paint —
    "references" (PubMed) and "cross_references" (the resolver fanout) are
    served later through their own entry points by the web shell.

    The remaining sources run in parallel: PubChem, Wikipedia, and
    PsychonautWiki are different hosts with different rate limits, so cold
    load drops from sum-of-sources to max-of-sources.
    """
    from concurrent.futures import ThreadPoolExecutor

    from chemica.sources.psychonaut import PsychonautWikiSource
    from chemica.sources.pubchem import PubChemSource
    from chemica.sources.pubmed import PubMedSource
    from chemica.sources.wikipedia import WikipediaSource

    pw = PsychonautWikiSource()
    with ThreadPoolExecutor(max_workers=5) as pool:
        tasks = {
            "compound": pool.submit(_try, PubChemSource().fetch_compound, name),
            "wikipedia": pool.submit(_try, WikipediaSource().fetch_article, name),
            "pw_article": pool.submit(_try, pw.fetch_article, name),
            "pw_profile": pool.submit(_try, pw.fetch_profile, name),
        }
        if "references" not in defer:
            tasks["references"] = pool.submit(
                _try, PubMedSource().fetch_references, name
            )
        results = {key: future.result() for key, future in tasks.items()}

    ladders, effects = results["pw_profile"] or ([], [])
    articles = [
        article
        for article in (results["wikipedia"], results["pw_article"])
        if article is not None
    ]
    cross_references = (
        []
        if "cross_references" in defer
        else _resolve_cross_references(name, articles, results["compound"])
    )

    return CompoundPage(
        compound=results["compound"],
        articles=articles,
        dose_ladders=ladders,
        effects=effects,
        references=results.get("references") or [],
        cross_references=cross_references,
    )


def fetch_references(name: str) -> list[Reference]:
    """Literature citations for the deferred references panel."""
    from chemica.sources.pubmed import PubMedSource

    return _try(PubMedSource().fetch_references, name) or []


def fetch_cross_references(name: str) -> list[CrossReference]:
    """Related-compound resolution for the deferred rail panel.

    Re-derives articles and the compound through the module-level caches —
    on the fragment path those are warm from the first paint.
    """
    articles = list(_article_sources(name))
    return _resolve_cross_references(name, articles, None)


def fetch_interactions(name: str) -> list[Interaction]:
    """PW interaction lines for the deferred interactions panel."""
    from chemica.sources.psychonaut import PsychonautWikiSource

    return _try(PsychonautWikiSource().fetch_interactions, name) or []


def fetch_hazards(name: str) -> HazardProfile | None:
    """GHS hazard data for the deferred hazards panel."""
    from chemica.sources.pubchem import PubChemSource

    source = PubChemSource()
    compound = _try(source.fetch_compound, name)
    if compound is None or compound.cid is None:
        return None
    return _try(source.fetch_hazards, compound.cid)


def _resolve_cross_references(
    name: str, articles: list[Article], compound: Compound | None
) -> list[CrossReference]:
    from chemica.crossrefs import extract_compound_mentions
    from chemica.sources.mediawiki import page_links as wiki_links
    from chemica.sources.mediawiki import section_links
    from chemica.sources.pubchem import PubChemSource
    from chemica.sources.wikipedia import API as WIKI_API

    source = PubChemSource()
    article_text = "\n".join(
        section.text for article in articles for section in article.sections
    )
    text_candidates = extract_compound_mentions(article_text)

    wiki_article = next(
        (a for a in articles if a.source == "wikipedia"), None
    )
    link_candidates: set[str] = set()
    if wiki_article:
        raw_titles = wiki_links(WIKI_API, wiki_article.title, limit=500)
        # A link is a real mention only if it appears in the article text,
        # filtering out navbox/template-only links (e.g. the Stimulants box).
        text_lower = article_text.lower()
        for title in raw_titles:
            clean = title.split("(")[0].strip()
            if clean.lower() in text_lower:
                link_candidates.add(clean)
            if len(link_candidates) >= 15:
                break
        # 'See also' is a human-curated related-compound list — filtered out
        # of the displayed article but kept as first-class candidates here.
        for title in section_links(WIKI_API, wiki_article.title, "see also"):
            link_candidates.add(title.split("(")[0].strip())

    # One batched resolution for every candidate: N name→CID lookups plus a
    # single properties call, instead of N full fetch_compound round-trips.
    resolved = source.fetch_many(list(link_candidates | text_candidates))

    # Merge: link candidates first — real Wikipedia links outrank regex
    # guesses on CID collision. by_cid keeps the first occurrence per
    # compound. Self-references are filtered by resolved CID, not the raw
    # query string, so aliases (Preludin → phenmetrazine) can't slip through.
    # On the deferred path `compound` may be None; resolve it lazily there.
    if compound is None:
        compound = source.fetch_compound(name)
    by_cid: dict[int, CrossReference] = {}
    for candidate in list(link_candidates) + list(text_candidates):
        target = resolved.get(candidate)
        if target is None or target.cid is None:
            continue
        if compound is not None and target.cid == compound.cid:
            continue
        # Class nouns ('insecticide') resolve to a representative compound
        # (indoxacarb) via PubChem's depositor synonyms — the card would show
        # a specific molecule under a generic label. Drop plain lowercase
        # words the record doesn't even title after the word; technical
        # names (MDPV, 2-MMC) and proper nouns (Adams' catalyst) are exempt.
        title = target.raw.get("Title")
        if (
            title
            and candidate.isalpha()
            and candidate.islower()
            and candidate.lower() not in title.lower()
        ):
            continue
        if target.cid not in by_cid:
            by_cid[target.cid] = CrossReference(candidate, target)
    return list(by_cid.values())[:12]


def _article_sources(name: str):
    """Yield each registered source's Article for the name, skipping declines."""
    from chemica.sources.psychonaut import PsychonautWikiSource
    from chemica.sources.pubmed import PubMedSource
    from chemica.sources.wikipedia import WikipediaSource

    for source in (WikipediaSource(), PsychonautWikiSource()):
        article = _try(source.fetch_article, name)
        if article is not None:
            yield article


def _try(fn, *args):
    """A source error becomes a decline, not a page failure."""
    try:
        return fn(*args)
    except Exception:
        return None
