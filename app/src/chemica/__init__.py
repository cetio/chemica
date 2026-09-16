"""chemica — a name becomes a sourced compound article.

The core package owns fetching and shaping. Web and desktop front-ends are thin
shells over it; nothing in here knows about FastAPI, GTK, or any delivery target.
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
