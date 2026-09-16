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
    """A Wikipedia article shaped into titled sections — the readable page."""

    title: str
    sections: list["Section"]
    url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Section:
    heading: str
    level: int
    text: str


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
    """Resolve a name to a sourced Article via the registered sources.

    First increment: Wikipedia only. Returns None if no source has the article.
    """
    from chemica.sources.wikipedia import WikipediaSource

    return WikipediaSource().fetch_article(name)
