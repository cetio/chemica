"""PubChem source — fetch a compound by name.

Uses the PubChem REST PUG API. The first increment maps a name to the property
infobox + identifiers; the blend/similarity path is out of scope.

Recorded fixtures (see tests/fixtures/) stand in for the live API in the pytest
suite so CI never depends on network reachability.
"""

from __future__ import annotations

import json
import re
from typing import Any

import requests

from chemica.core import Article, Compound

# CAS Registry Numbers look like 58-08-2: 2-7 digits, dash, 2 digits, dash, 1 digit.
_CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"


def _cas(synonyms: list[str]) -> str | None:
    """The CAS RN is a numeric-only synonym — the first match wins."""
    for s in synonyms:
        if _CAS_RE.match(s):
            return s
    return None


class PubChemSource:
    name = "pubchem"

    def fetch_compound(self, query: str) -> Compound | None:
        cid = self._name_to_cid(query)
        if cid is None:
            return None
        props = self._properties(cid)
        return self._shape(query, cid, props)

    def fetch_article(self, query: str) -> Article | None:
        return None

    def _name_to_cid(self, name: str) -> int | None:
        url = f"{PUG}/compound/name/{requests.utils.quote(name)}/cids/JSON"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        body = resp.json()
        cids = body.get("IdentifierList", {}).get("CID", [])
        return cids[0] if cids else None

    def _properties(self, cid: int) -> dict[str, Any]:
        props = "MolecularFormula,MolecularWeight,MonoisotopicMass,Charge,TPSA,XLogP,ConnectivitySMILES,InChI,InChIKey"
        url = f"{PUG}/compound/cid/{cid}/property/{props}/JSON"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return {}
        table = resp.json().get("PropertyTable", {}).get("Properties", [])
        return table[0] if table else {}

    def _shape(self, query: str, cid: int, props: dict[str, Any]) -> Compound:
        synonyms = self._synonyms(cid)
        return Compound(
            # First letter only — .title() would mangle "DMT"/"5-HTP".
            name=query[:1].upper() + query[1:],
            cid=cid,
            formula=props.get("MolecularFormula"),
            molecular_weight=_float(props.get("MolecularWeight")),
            mass=_float(props.get("MonoisotopicMass")),
            charge=_int(props.get("Charge")),
            tpsa=_float(props.get("TPSA")),
            xlogp=_float(props.get("XLogP")),
            smiles=props.get("ConnectivitySMILES"),
            inchi=props.get("InChI"),
            inchikey=props.get("InChIKey"),
            cas=_cas(synonyms),
            synonyms=synonyms,
            raw=props,
        )

    def _synonyms(self, cid: int) -> list[str]:
        url = f"{PUG}/compound/cid/{cid}/synonyms/JSON"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return []
        info = resp.json().get("InformationList", {}).get("Information", [])
        return info[0].get("Synonym", []) if info else []


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
