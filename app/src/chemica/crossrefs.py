"""Cross-references — rabbit holes.

Given an article's plain text, find compound names mentioned inside it, resolve them
against PubChem (or any resolver), and return the ones that map to real compounds.

This is the graph feature the D app called `resolveCompoundLinks`. The algorithm is
heuristic (suffix matching, IUPAC-style names, number-prefixed compounds) plus a
resolution filter: candidates that don't resolve to a compound are discarded.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from chemica.core import Compound, CrossReference

# Pharmaceutical/drug suffixes (5+ chars to reduce false positives).
SUFFIXES = [
    "amine", "azine", "azole", "caine", "cillin",
    "cline", "idine", "mycin", "ophen", "orphan",
    "profen", "ridol", "sartan", "setron", "statin",
    "tadine", "terol", "thiazide", "tidine", "tinib",
    "triptan", "xaban", "zepam", "zodone", "zosin",
    "olol", "pril", "oxin",
]

# Common English words that happen to match a drug suffix but are not compounds.
EXCLUDED = {
    "determine", "examine", "famine", "machine", "routine", "pristine",
    "magazine", "alpine", "discipline", "doctrine", "medicine", "gasoline",
    "genuine", "imagine", "feminine", "masculine", "antine", "decline",
    "combine", "online", "done", "gone", "bone", "tone", "zone", "phone",
    "pine", "mine", "fine", "line", "wine", "vine", "undermine", "sunshine",
    "outline",
}

_WORD_RE = re.compile(r"\b[\w]{6,}\b")
_IUPAC_RE = re.compile(r"\d+(?:,\d+)*-\([A-Za-z,]+\)-[A-Za-z][A-Za-z0-9-]*")
_NUM_RE = re.compile(r"\d+-?[A-Z][A-Za-z0-9]*(?:-[A-Z][A-Za-z0-9]*)+")


def find_cross_references(
    text: str, resolver: Callable[[str], Compound | None]
) -> list[CrossReference]:
    """Return all compound mentions in *text* that resolve to a real compound."""
    candidates = extract_compound_mentions(text)
    return resolve_candidates(candidates, resolver)


def resolve_candidates(
    candidates: set[str], resolver: Callable[[str], Compound | None], max_workers: int = 5
) -> list[CrossReference]:
    """Resolve a set of candidate names in parallel and return the compounds."""
    ret: list[CrossReference] = []
    seen: set[int] = set()

    def safe_resolve(name: str) -> tuple[str, Compound | None]:
        try:
            return name, resolver(name)
        except Exception:
            return name, None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(safe_resolve, name) for name in candidates]
        for future in as_completed(futures):
            name, compound = future.result()
            if compound is None:
                continue
            key = compound.cid if compound.cid is not None else id(compound)
            if key in seen:
                continue
            seen.add(key)
            ret.append(CrossReference(name, compound))
    return ret


def extract_compound_mentions(text: str) -> set[str]:
    """Find candidate compound names in plain text using heuristics.

    The matches are intentionally over-eager; the resolution step filters them.
    """
    names: set[str] = set()

    # Drug-suffix heuristic.
    for match in _WORD_RE.finditer(text):
        word = match.group(0)
        if _has_drug_suffix(word):
            names.add(word)

    # IUPAC-style names.
    for match in _IUPAC_RE.finditer(text):
        names.add(match.group(0))

    # Number-prefixed compounds (2C-B, 5-MeO-DMT, etc.).
    for match in _NUM_RE.finditer(text):
        names.add(match.group(0))

    return names


def _has_drug_suffix(word: str) -> bool:
    lower = word.lower()
    if lower in EXCLUDED:
        return False
    for suffix in SUFFIXES:
        if len(lower) > len(suffix) and lower.endswith(suffix):
            return True
    return False
