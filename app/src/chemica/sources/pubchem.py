"""PubChem source — fetch a compound by name.

Uses the PubChem REST PUG API. The first increment maps a name to the property
infobox + identifiers; the blend/similarity path is out of scope.

Recorded fixtures (see tests/fixtures/) stand in for the live API in the pytest
suite so CI never depends on network reachability.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests

from chemica.core import Article, Compound

# CAS Registry Numbers look like 58-08-2: 2-7 digits, dash, 2 digits, dash, 1 digit.
_CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

# Name → resolved Compound. Module-level because the core instantiates fresh
# PubChemSource objects per call — an instance cache would never see a repeat.
# Names are stable, so entries never expire; the cache dies with the process.
_CACHE: dict[str, Compound | None] = {}

# Name → CID, shared by fetch_compound and fetch_many so a compound resolved
# once never re-pays the lookup.
_CID_CACHE: dict[str, int | None] = {}


def _cas(synonyms: list[str]) -> str | None:
    """The CAS RN is a numeric-only synonym — the first match wins."""
    for s in synonyms:
        if _CAS_RE.match(s):
            return s
    return None


class PubChemSource:
    name = "pubchem"

    def fetch_compound(self, query: str) -> Compound | None:
        key = query.strip().lower()
        if key not in _CACHE:
            _CACHE[key] = self._uncached(query)
        return _CACHE[key]

    def _uncached(self, query: str) -> Compound | None:
        cid = self._name_to_cid(query)
        if cid is None:
            return None
        props = self._properties(cid)
        return self._shape(query, cid, props)

    def fetch_article(self, query: str) -> Article | None:
        return None

    def fetch_many(self, queries: list[str]) -> dict[str, Compound | None]:
        """Resolve many names cheaply: parallel name→CID, then one batched
        properties call. Skips synonyms — cross-ref cards only need the
        formula — so results are lighter than fetch_compound's and never
        enter _CACHE."""
        ret: dict[str, Compound | None] = {}
        pending = [
            q
            for q in dict.fromkeys(queries)
            if q.strip().lower() not in _CACHE
        ]
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {pool.submit(self._name_to_cid, q): q for q in pending}
            cid_for = {}
            for future in as_completed(futures):
                try:
                    cid_for[futures[future]] = future.result()
                except Exception:
                    cid_for[futures[future]] = None
        cids = {cid for cid in cid_for.values() if cid is not None}
        props_by_cid = self._properties_batch(sorted(cids)) if cids else {}
        for query in pending:
            cid = cid_for.get(query)
            ret[query] = (
                self._shape(query, cid, props_by_cid.get(cid, {}), synonyms=[])
                if cid is not None
                else None
            )
        for query in queries:
            key = query.strip().lower()
            ret.setdefault(query, _CACHE.get(key))
        return ret

    def _name_to_cid(self, name: str) -> int | None:
        key = name.strip().lower()
        if key in _CID_CACHE:
            return _CID_CACHE[key]
        url = f"{PUG}/compound/name/{requests.utils.quote(name)}/cids/JSON"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            _CID_CACHE[key] = None
            return None
        body = resp.json()
        cids = body.get("IdentifierList", {}).get("CID", [])
        _CID_CACHE[key] = cids[0] if cids else None
        return _CID_CACHE[key]

    def _properties_batch(self, cids: list[int]) -> dict[int, dict[str, Any]]:
        """One call for many CIDs — PubChem accepts a comma-separated list."""
        props = "MolecularFormula,MolecularWeight,MonoisotopicMass,Charge,TPSA,XLogP,ConnectivitySMILES,InChI,InChIKey"
        url = f"{PUG}/compound/cid/{','.join(str(c) for c in cids)}/property/{props}/JSON"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return {}
        table = resp.json().get("PropertyTable", {}).get("Properties", [])
        return {row["CID"]: row for row in table if "CID" in row}

    def _properties(self, cid: int) -> dict[str, Any]:
        return self._properties_batch([cid]).get(cid, {})

    def _shape(
        self,
        query: str,
        cid: int,
        props: dict[str, Any],
        synonyms: list[str] | None = None,
    ) -> Compound:
        if synonyms is None:
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
