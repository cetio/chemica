"""FastAPI web shell over the chemica core.

Two pages: the search home and the compound article. The shell holds no fetch
logic of its own — every call goes through `chemica.core`, whose sources stay
pluggable and whose seam the desktop app reuses.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from chemica.core import Compound, fetch_compound_page

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
app.mount("/static", StaticFiles(directory=str(TEMPLATES_DIR.parent / "static")), name="static")


def _display(value: Any) -> str:
    """Page text for a field: whole floats lose the trailing .0, None becomes --."""
    if value is None:
        return "--"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _infobox_groups(compound: Compound) -> list[tuple[str, list[tuple[str, str]]]]:
    return [
        ("Identifiers", [(label, _display(get(compound))) for label, get in IDENTIFIER_ROWS]),
        ("Properties", [(label, _display(get(compound))) for label, get in PROPERTY_ROWS]),
    ]


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
    page = fetch_compound_page(name)

    if page.compound is None and not page.articles:
        return templates.TemplateResponse(
            request, "not_found.html", {"query": name}, status_code=404
        )

    compound = page.compound

    by_source = {a.source: a for a in page.articles if a.source}
    article = (
        by_source.get("wikipedia")
        or by_source.get("psychonautwiki")
        or (page.articles[0] if page.articles else None)
    )
    return templates.TemplateResponse(
        request,
        "article.html",
        {
            "compound": compound,
            "article": article,
            "infobox": _infobox_groups(compound) if compound else [],
            "dosages": page.dose_ladders,
            "effects": page.effects,
            "references": page.references,
            "cross_references": page.cross_references,
        },
    )


@app.get("/structure/{cid}.png")
def structure_image(cid: int) -> Response:
    """Proxy PubChem's structure PNG so browser rate-limits don't blank it."""
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/PNG"
    resp = requests.get(url, timeout=15, headers={"User-Agent": "chemica/0.1"})
    if resp.status_code != 200:
        return Response(status_code=resp.status_code)
    return Response(
        content=resp.content,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
