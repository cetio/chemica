"""PubChem source — fetch a compound by name.

Uses the PubChem REST PUG API. The first increment maps a name to the property
infobox + identifiers; the blend/similarity path is out of scope.

Recorded fixtures (see tests/fixtures/) stand in for the live API in the pytest
suite so CI never depends on network reachability.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from typing import Any

import requests

from chemica import cache
from chemica.core import Article, Compound, DrugProfile, HazardProfile

# CAS Registry Numbers look like 58-08-2: 2-7 digits, dash, 2 digits, dash, 1 digit.
_CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")

# Element symbols in a SMILES fragment — used to pick the largest fragment of
# a dot-disconnected (salt/mixture) record.
_ATOM_RE = re.compile(r"[A-Z][a-z]?")

# PubChem's 'Drug Classes' mixes MeSH check tags (population/species
# descriptors like 'Lactation' or 'Humans') into the pharmacological-action
# classes. Denylist the check-tag set so the card shows drug classes only.
_MESH_CHECKTAGS = {
    "animals",
    "humans",
    "male",
    "female",
    "pregnancy",
    "breast feeding",
    "lactation",
    "milk, human",
    "infant",
    "infant, newborn",
    "child",
    "adolescent",
    "adult",
    "middle aged",
    "aged",
    "young adult",
}

# PUG-View appends 'For more X data … please visit the HSDB record page'
# pointer rows to long sections — navigation chrome, not data.
_POINTER_RE = re.compile(r"for more .*data for .*please visit", re.IGNORECASE)

PUG = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

# Property set shared by single and batched fetches.
_PROPS = "Title,MolecularFormula,MolecularWeight,MonoisotopicMass,Charge,TPSA,XLogP,ConnectivitySMILES,InChI,InChIKey"

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
            # Misses are not memoized — see mediawiki.resolve_title.
            compound = self._uncached(query)
            if compound is not None:
                _CACHE[key] = compound
            return compound
        return _CACHE[key]

    def _uncached(self, query: str) -> Compound | None:
        cid = self._name_to_cid(query)
        if cid is None:
            # PubChem's synonym list misses slang/abbreviations PubChem users
            # do search by ('MXiPr' → Methoxisopropamine). Wikipedia's title
            # resolver knows the canonical name — retry once through it.
            from chemica.sources import mediawiki
            from chemica.sources.wikipedia import API as WIKI_API

            canonical = mediawiki.resolve_title(WIKI_API, query)
            if canonical and canonical.lower() != query.strip().lower():
                cid = self._name_to_cid(canonical)
        if cid is None:
            return None
        props = self._properties(cid)
        base_cid = self._freebase_cid(props)
        if base_cid is not None and base_cid != cid:
            base_props = self._properties(base_cid)
            if base_props:
                return self._shape(query, base_cid, base_props, salt_form=props.get("Title"))
        return self._shape(query, cid, props)

    def _freebase_cid(self, props: dict[str, Any]) -> int | None:
        """Dot-disconnected SMILES marks a salt/mixture record — the largest
        fragment is the drug, the rest is counterion or water. fastidentity
        on that fragment lands on the freebase CID ('...Cl' salts, hydrates)."""
        smiles = props.get("ConnectivitySMILES") or ""
        if "." not in smiles:
            return None
        largest = max(smiles.split("."), key=lambda f: len(_ATOM_RE.findall(f)))
        url = f"{PUG}/compound/fastidentity/smiles/{requests.utils.quote(largest, safe='')}/cids/JSON"
        resp = cache.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        cids = resp.json().get("IdentifierList", {}).get("CID", [])
        return cids[0] if cids else None

    def fetch_article(self, query: str) -> Article | None:
        return None

    def fetch_many(self, queries: list[str]) -> dict[str, Compound | None]:
        """Resolve many names cheaply: parallel name→CID, then one batched
        properties call. Skips synonyms — cross-ref cards only need the
        formula — so results are lighter than fetch_compound's and never
        enter _CACHE."""
        ret: dict[str, Compound | None] = {}
        pending = [q for q in dict.fromkeys(queries) if q.strip().lower() not in _CACHE]
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
            ret[query] = self._shape(query, cid, props_by_cid.get(cid, {}), synonyms=[]) if cid is not None else None
        for query in queries:
            key = query.strip().lower()
            ret.setdefault(query, _CACHE.get(key))
        return ret

    def _name_to_cid(self, name: str) -> int | None:
        key = name.strip().lower()
        if key in _CID_CACHE:
            return _CID_CACHE[key]
        url = f"{PUG}/compound/name/{requests.utils.quote(name)}/cids/JSON"
        resp = cache.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        body = resp.json()
        cids = body.get("IdentifierList", {}).get("CID", [])
        if not cids:
            return None
        _CID_CACHE[key] = cids[0]
        return _CID_CACHE[key]

    def _properties_batch(self, cids: list[int]) -> dict[int, dict[str, Any]]:
        """One call for many CIDs — PubChem accepts a comma-separated list."""
        url = f"{PUG}/compound/cid/{','.join(str(c) for c in cids)}/property/{_PROPS}/JSON"
        resp = cache.get(url, timeout=15)
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
        salt_form: str | None = None,
    ) -> Compound:
        if synonyms is None:
            synonyms = self._synonyms(cid)
        return Compound(
            # Prefer the record's title so aliases render under the canonical
            # name ('Special K' → Ketamine, 'Preludin' → Phenmetrazine). The
            # queried term stays visible in the URL and the salt_form note.
            # Fallback: first letter only — .title() would mangle "DMT", and
            # .upper() on non-ASCII turns α-PVP into Α-PVP (Greek capital).
            name=props.get("Title")
            or (query[:1].upper() + query[1:] if query[:1].isascii() and query[:1].islower() else query),
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
            salt_form=salt_form,
            synonyms=synonyms,
            raw=props,
        )

    def _synonyms(self, cid: int) -> list[str]:
        url = f"{PUG}/compound/cid/{cid}/synonyms/JSON"
        resp = cache.get(url, timeout=15)
        if resp.status_code != 200:
            return []
        info = resp.json().get("InformationList", {}).get("Information", [])
        return info[0].get("Synonym", []) if info else []

    def fetch_drug_profile(self, cid: int) -> DrugProfile | None:
        """Regulatory/clinical identity via PUG-View's drug section — one
        call, heading-scoped. Sparse/absent on research-chem records, which
        decline honestly (None)."""
        url = (
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/"
            f"compound/{cid}/JSON?heading=Drug+and+Medication+Information"
        )
        resp = cache.get(url, timeout=20)
        if resp.status_code != 200:
            return None
        root = resp.json().get("Record", {}).get("Section", [])
        # Half-life lives under a different top-level heading — one extra
        # scoped call rather than pulling the whole record unscoped.
        pharma_url = (
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/"
            f"compound/{cid}/JSON?heading=Pharmacology+and+Biochemistry"
        )
        pharma_resp = cache.get(pharma_url, timeout=20)
        pharma_root = pharma_resp.json().get("Record", {}).get("Section", []) if pharma_resp.status_code == 200 else []
        profile = DrugProfile()
        for heading in (
            "Max Phase",
            "First Approval",
            "Availability Type",
            "Route of Administration",
            "Drug Classes",
            "Biological Half-Life",
            "Black Box Warning",
        ):
            scope = pharma_root if heading == "Biological Half-Life" else root
            section = _find_section(scope, heading)
            if section is None:
                continue
            values = _info_values(section)
            if not values:
                continue
            if heading == "Max Phase":
                profile = replace(profile, max_phase=values[0])
            elif heading == "First Approval":
                profile = replace(profile, first_approval=_int(values[0]))
            elif heading == "Availability Type":
                profile = replace(profile, availability=values[0])
            elif heading == "Route of Administration":
                profile = replace(profile, routes=values)
            elif heading == "Drug Classes":
                classes = values[0].split(";")
                profile = replace(
                    profile,
                    drug_classes=[c.strip() for c in classes if c.strip() and c.strip().lower() not in _MESH_CHECKTAGS],
                )
            elif heading == "Biological Half-Life":
                profile = replace(
                    profile,
                    half_life=[v for v in values if not _POINTER_RE.search(v)],
                )
            elif heading == "Black Box Warning":
                profile = replace(profile, black_box=values[0].strip().lower() == "yes")
        if profile == DrugProfile():
            return None
        return profile

    def fetch_by_cids(self, cids: list[int]) -> dict[int, Compound]:
        """Light compounds for known CIDs — one batched properties call,
        synonyms skipped (xref cards only show formula/thumb)."""
        props_by_cid = self._properties_batch(cids)
        return {
            cid: self._shape(props["Title"], cid, props, synonyms=[])
            for cid, props in props_by_cid.items()
            if props.get("Title")
        }

    def fetch_similar(self, cid: int, limit: int = 8) -> list[int]:
        """2D-structural neighbors — the related-compounds backstop for
        compounds whose Wikipedia article has few outlinks (thin RC pages).
        PubChem returns the query CID first; caller filters it."""
        url = (
            f"{PUG}/compound/fastsimilarity_2d/cid/{cid}/cids/JSON"
            f"?MaxRecords={limit}"
        )
        resp = cache.get(url, timeout=15)
        if resp.status_code != 200:
            return []
        return resp.json().get("IdentifierList", {}).get("CID", [])

    def fetch_hazards(self, cid: int) -> HazardProfile | None:
        """GHS classification via PUG-View: pictograms, signal word, and
        H-statements, deduplicated across the notifier entries."""
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=Safety+and+Hazards"
        resp = cache.get(url, timeout=20)
        if resp.status_code != 200:
            return None
        section = _find_section(
            resp.json().get("Record", {}).get("Section", []),
            "GHS Classification",
        )
        if section is None:
            return None
        pictograms: list[str] = []
        signal: str | None = None
        statements: list[str] = []
        for info in section.get("Information", []):
            strings = [item.get("String", "") for item in info.get("Value", {}).get("StringWithMarkup", [])]
            name = info.get("Name")
            if name == "Pictogram(s)":
                for item in info["Value"].get("StringWithMarkup", []):
                    for markup in item.get("Markup", []):
                        code = markup.get("URL", "").rsplit("/", 1)[-1].removesuffix(".svg")
                        if code.startswith("GHS") and code not in pictograms:
                            pictograms.append(code)
            elif name == "Signal":
                for s in strings:
                    if s.strip() == "Danger":
                        signal = "Danger"
                    elif s.strip() == "Warning" and signal is None:
                        signal = "Warning"
            elif name == "GHS Hazard Statements":
                for s in strings:
                    text = s.strip()
                    if text and text not in statements:
                        statements.append(text)
        if not (pictograms or signal or statements):
            return None
        return HazardProfile(pictograms=pictograms, signal=signal, statements=statements)


def _info_values(section: dict) -> list[str]:
    """Flatten a PUG-View section's Information values to plain strings —
    StringWithMarkup strings first, then raw Numbers (First Approval year)."""
    ret: list[str] = []
    for info in section.get("Information", []):
        value = info.get("Value", {})
        for item in value.get("StringWithMarkup", []):
            s = item.get("String", "").strip()
            if s:
                ret.append(s)
        for number in value.get("Number", []):
            ret.append(str(number))
    return ret


def _find_section(sections: list[dict], heading: str) -> dict | None:
    for section in sections:
        if section.get("TOCHeading") == heading:
            return section
        found = _find_section(section.get("Section", []), heading)
        if found is not None:
            return found
    return None


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
