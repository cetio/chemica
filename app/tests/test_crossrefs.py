"""Tests for chemica.crossrefs — the rabbit-hole detector."""

from __future__ import annotations

from chemica import Compound
from chemica.crossrefs import extract_compound_mentions, find_cross_references


def test_extract_compound_mentions_finds_drug_suffixes():
    text = (
        "Aspirin is related to ketamine and ibuprofen. "
        "Machine learning and medicine are not compounds."
    )
    mentions = extract_compound_mentions(text)
    assert "ketamine" in mentions
    assert "ibuprofen" in mentions
    assert "machine" not in mentions
    assert "medicine" not in mentions


def test_extract_compound_mentions_finds_iupac_and_number_prefixed():
    text = "2C-B and 5-MeO-DMT are psychedelics. 4-AcO-DMT is a prodrug."
    mentions = extract_compound_mentions(text)
    assert "2C-B" in mentions
    assert "5-MeO-DMT" in mentions
    assert "4-AcO-DMT" in mentions


def test_find_cross_references_resolves_only_known_compounds():
    resolved = {"aspirin", "ibuprofen"}

    def resolver(name: str) -> Compound | None:
        if name.lower() in resolved:
            return Compound(name=name)
        return None

    text = "Paracetamol is sometimes combined with ibuprofen or with a fictional compound."
    refs = find_cross_references(text, resolver)
    names = {ref.name for ref in refs}

    assert "ibuprofen" in names
    assert len(refs) == 1
