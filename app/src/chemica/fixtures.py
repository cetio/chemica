"""Fixture recording harness for the pytest suite.

a writes the tests first against recorded fixtures; this module is how those
fixtures get recorded once (against the live API) and replayed forever after.

Usage:

    # Record (run once, with network, when a source's API shape changes):
    python -m chemica.fixtures record aspirin

    # Replay (default in tests): fetch_compound/fetch_article read from disk
    # and never touch the network.

The harness snapshots per-endpoint raw API responses (not shaped payloads) so
the conftest replay layer reads exactly what the live API returned. File names
match the conftest URL→fixture map: cids_{name}.json, properties_{cid}.json,
synonyms_{cid}.json for PubChem; query_{name}.json, summary_{name}.json for
Wikipedia.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

import requests

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_REST = "https://en.wikipedia.org/api/rest_v1"


def record(query: str) -> None:
    """Hit the live sources once and snapshot the raw per-endpoint responses."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    _record_pubchem(query)
    _record_wikipedia(query)


def _record_pubchem(query: str) -> None:
    pubchem_dir = FIXTURE_DIR / "pubchem"
    pubchem_dir.mkdir(parents=True, exist_ok=True)

    # cids endpoint — keyed by compound name
    cids_url = f"{PUG}/compound/name/{quote(query)}/cids/JSON"
    cids_resp = requests.get(cids_url, timeout=15)
    if cids_resp.status_code != 200:
        return
    cids_body = cids_resp.json()
    _write(pubchem_dir / f"cids_{_safe(query)}.json", cids_body)
    cids = cids_body.get("IdentifierList", {}).get("CID", [])
    if not cids:
        return
    cid = cids[0]

    # properties endpoint — keyed by CID
    props = "MolecularFormula,MolecularWeight,MonoisotopicMass,Charge,TPSA,XLogP,ConnectivitySMILES,InChI,InChIKey"
    props_url = f"{PUG}/compound/cid/{cid}/property/{props}/JSON"
    props_resp = requests.get(props_url, timeout=15)
    if props_resp.status_code == 200:
        _write(pubchem_dir / f"properties_{cid}.json", props_resp.json())

    # synonyms endpoint — keyed by CID
    syn_url = f"{PUG}/compound/cid/{cid}/synonyms/JSON"
    syn_resp = requests.get(syn_url, timeout=15)
    if syn_resp.status_code == 200:
        _write(pubchem_dir / f"synonyms_{cid}.json", syn_resp.json())


def _record_wikipedia(query: str) -> None:
    wiki_dir = FIXTURE_DIR / "wikipedia"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    # query endpoint — keyed by compound name
    query_url = f"{WIKI_API}?action=query&titles={quote(query)}&format=json&redirects=1"
    query_resp = requests.get(query_url, timeout=15)
    if query_resp.status_code != 200:
        return
    query_body = query_resp.json()
    _write(wiki_dir / f"query_{_safe(query)}.json", query_body)
    pages = query_body.get("query", {}).get("pages", {})
    if not pages:
        return
    page = next(iter(pages.values()))
    if "missing" in page:
        return
    title = page.get("title", query)

    # summary endpoint — keyed by resolved title
    summary_url = f"{WIKI_REST}/page/summary/{quote(title)}"
    summary_resp = requests.get(summary_url, timeout=15)
    if summary_resp.status_code == 200:
        _write(wiki_dir / f"summary_{_safe(title)}.json", summary_resp.json())


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _safe(name: str) -> str:
    return name.replace(" ", "_").replace("/", "_")


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "record":
        record(sys.argv[2] if len(sys.argv) > 2 else "aspirin")
    else:
        print("usage: python -m chemica.fixtures record [name]")
