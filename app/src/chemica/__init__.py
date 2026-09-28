"""Chemica core: fetch and shape compound articles from upstream sources.

This package owns fetching and shaping. Front-ends are thin shells over it, and
nothing here depends on a delivery target such as FastAPI or GTK.
"""

from chemica.core import (
    Article,
    Compound,
    CompoundPage,
    CrossReference,
    DoseLadder,
    EffectsProfile,
    Reference,
    fetch_article,
    fetch_compound,
    fetch_compound_page,
)

__all__ = [
    "Article",
    "Compound",
    "CompoundPage",
    "CrossReference",
    "DoseLadder",
    "EffectsProfile",
    "Reference",
    "fetch_article",
    "fetch_compound",
    "fetch_compound_page",
]
