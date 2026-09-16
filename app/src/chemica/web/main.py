"""FastAPI web shell over the chemica core.

Two pages: the search home and the compound article. The shell holds no fetch
logic of its own — every call goes through `chemica.core`, whose sources stay
pluggable and whose seam the desktop app reuses.
"""

from __future__ import annotations

import re
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from chemica.core import (
    Compound,
    fetch_compound_page,
    fetch_cross_references,
    fetch_drug_profile,
    fetch_hazards,
    fetch_interactions,
    fetch_references,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"

# Which fields the infobox shows, in display order. Each entry pairs the row
# label with the getter; absent fields render as "--" rather than vanishing,
# so the page stays honest about what the source did not provide.
IDENTIFIER_ROWS: list[tuple[str, Any]] = [
    ("CID", lambda c: c.cid),
    ("Formula", lambda c: c.formula),
    ("SMILES", lambda c: c.smiles),
    ("InChI", lambda c: c.inchi),
    ("InChIKey", lambda c: c.inchikey),
    ("CAS", lambda c: c.cas),
]

PROPERTY_ROWS: list[tuple[str, Any]] = [
    ("Weight", lambda c: c.molecular_weight),
    ("Mass", lambda c: c.mass),
    ("Charge", lambda c: c.charge),
    ("TPSA", lambda c: c.tpsa),
    ("XLogP", lambda c: c.xlogp),
]

app = FastAPI(title="Chemica")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["subscript"] = lambda value: re.sub(r"\d+", lambda m: f"<sub>{m.group()}</sub>", value or "")
app.mount("/static", StaticFiles(directory=str(TEMPLATES_DIR.parent / "static")), name="static")


def _display(value: Any) -> str:
    """Page text for a field: whole floats lose the trailing .0, None becomes —."""
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _infobox_groups(compound: Compound) -> list[tuple[str, list[tuple[str, str]]]]:
    return [
        ("Identifiers", [(label, _display(get(compound))) for label, get in IDENTIFIER_ROWS]),
        ("Properties", [(label, _display(get(compound))) for label, get in PROPERTY_ROWS]),
    ]


def _section_tree(sections: list[Any]) -> list[tuple[Any, list]]:
    """Nest flat sections by heading level into (section, children) pairs."""
    tree: list[tuple[Any, list]] = []
    stack: list[tuple[int, list]] = [(-1, tree)]
    for section in sections:
        while stack[-1][0] >= section.level:
            stack.pop()
        node = (section, [])
        stack[-1][1].append(node)
        stack.append((section.level, node[1]))
    return tree


_PHASES = ("onset", "comeup", "peak", "offset", "aftereffects")


def _minutes(text: str | None) -> float | None:
    """Mean of a source range string in minutes ("5 - 10 minutes" -> 7.5)."""
    if not text:
        return None
    nums = re.findall(r"\d+(?:\.\d+)?", text)
    if not nums:
        return None
    value = sum(float(n) for n in nums) / len(nums)
    if re.search(r"\bhours?\b|\d\s*h\b", text, re.IGNORECASE):
        return value * 60
    if re.search(r"\bseconds?\b|\d\s*s\b", text, re.IGNORECASE):
        return value / 60
    return value


def _segments(effect: Any) -> list[dict[str, Any]]:
    spans = [(phase, _minutes(getattr(effect, phase)), getattr(effect, phase)) for phase in _PHASES]
    total = sum(width for _, width, _ in spans if width)
    if not total:
        return []
    cursor = 0.0
    segments = []
    for phase, width, raw in spans:
        if not width:
            continue
        segments.append({"phase": phase, "left": 100 * cursor / total, "width": 100 * width / total, "label": raw})
        cursor += width
    return segments


@app.get("/", response_class=HTMLResponse)
def search(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "search.html")


@app.get("/search")
def submit(request: Request, q: str = "") -> HTMLResponse:
    name = q.strip()
    if not name:
        return templates.TemplateResponse(request, "search.html")
    return RedirectResponse(f"/compound/{name}", status_code=303)


@app.get("/compound/{name}", response_class=HTMLResponse)
def compound_page(request: Request, name: str) -> HTMLResponse:
    page = fetch_compound_page(name, defer={"references", "cross_references"})

    if page.compound is None and not page.articles:
        return templates.TemplateResponse(request, "not_found.html", {"query": name}, status_code=404)

    compound = page.compound

    by_source = {a.source: a for a in page.articles if a.source}
    article = (
        by_source.get("wikipedia") or by_source.get("psychonautwiki") or (page.articles[0] if page.articles else None)
    )
    title = compound.name if compound else article.title
    if title[:1].isascii() and title[:1].islower():
        title = title[:1].upper() + title[1:]
    return templates.TemplateResponse(
        request,
        "article.html",
        {
            "title": title,
            "name": name,
            "compound": compound,
            "classes": page.classes,
            "article": article,
            "infobox": _infobox_groups(compound) if compound else [],
            "section_tree": _section_tree(article.sections[1:]) if article else [],
            "dosages": [replace(d, bioavailability=_clean_field(d.bioavailability)) for d in page.dose_ladders],
            "timelines": [{"route": e.route, "total": e.total, "segments": _segments(e)} for e in page.effects],
        },
    )


@app.get("/compound/{name}/references", response_class=HTMLResponse)
def references_fragment(request: Request, name: str) -> HTMLResponse:
    """Deferred PubMed panel — loaded by fragments.js after first paint."""
    return templates.TemplateResponse(request, "_references.html", {"references": fetch_references(name)})


@app.get("/compound/{name}/cross-references")
def cross_references_fragment(request: Request, name: str) -> Response:
    """Deferred related-compounds rail — empty result removes the slot."""
    xrefs = fetch_cross_references(name)
    if not xrefs:
        return Response(status_code=204)
    return templates.TemplateResponse(request, "_cross_refs.html", {"cross_references": xrefs})


_STMT_RE = re.compile(r"^(H\d+)\s*(?:\(([\d.]+)%\))?:\s*(.*?)\s*(?:\[[^\]]*\])?\s*$")
_CITE_RE = re.compile(r"\{\{[^{}]*\}\}|\{\{.*|<ref[^>]*/>|<ref[^>]*>.*?</ref>", re.S)


def _clean_field(text: str | None) -> str | None:
    """Drop citation markup a source left in a short display field."""
    return _CITE_RE.sub("", text).strip() if text else text


def _clean_statements(statements: list[str]) -> list[dict[str, Any]]:
    """Dedupe H-statements by code, keeping the highest notifier percentage."""
    best: dict[str, dict[str, Any]] = {}
    for stmt in statements:
        m = _STMT_RE.match(stmt)
        if not m:
            continue
        code, pct, text = m.group(1), m.group(2), m.group(3)
        entry = {"code": code, "text": text, "pct": float(pct) if pct else None}
        if code not in best or (entry["pct"] or 0) > (best[code]["pct"] or 0):
            best[code] = entry
    return list(best.values())


@app.get("/compound/{name}/interactions", response_class=HTMLResponse)
def interactions_fragment(request: Request, name: str) -> HTMLResponse:
    """Deferred PW dangerous-interactions card — data or decline."""
    return templates.TemplateResponse(request, "_interactions.html", {"interactions": fetch_interactions(name)})


@app.get("/compound/{name}/drug-profile", response_class=HTMLResponse)
def drug_profile_fragment(request: Request, name: str) -> HTMLResponse:
    """Deferred PubChem drug-profile card — data or decline."""
    return templates.TemplateResponse(request, "_drug_profile.html", {"profile": fetch_drug_profile(name)})


@app.get("/compound/{name}/hazards", response_class=HTMLResponse)
def hazards_fragment(request: Request, name: str) -> HTMLResponse:
    """Deferred GHS hazard card — the slot always settles, data or decline."""
    hazards = fetch_hazards(name)
    return templates.TemplateResponse(
        request,
        "_hazards.html",
        {
            "hazards": hazards,
            "statements": _clean_statements(hazards.statements) if hazards else [],
        },
    )


@app.get("/sdf/{cid}")
def structure_sdf(cid: int) -> Response:
    """Proxy PubChem's 3D conformer SDF for the 3Dmol.js viewer."""
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/SDF?record_type=3d"
    resp = None
    for attempt in range(3):
        resp = requests.get(url, timeout=15, headers={"User-Agent": "chemica/0.1"})
        if resp.status_code not in (429, 503):
            break
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))
    if resp is None or resp.status_code != 200:
        return Response(status_code=503)
    return Response(
        content=resp.content,
        media_type="chemical/x-mdl-sdfile",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/structure/{cid}.png")
def structure_image(cid: int) -> Response:
    """Proxy PubChem's structure PNG so browser rate-limits don't blank it."""
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/PNG"
    resp = None
    for attempt in range(3):
        resp = requests.get(url, timeout=15, headers={"User-Agent": "chemica/0.1"})
        if resp.status_code not in (429, 503):
            break
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))
    if resp is None or resp.status_code != 200:
        return Response(status_code=503)
    return Response(
        content=resp.content,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
