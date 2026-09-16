# Contributing to Chemica

Chemica turns a substance name into a readable, sourced article. This document
covers the dev loop; the working agreements for the shared tree live in
`AGENTS.md`, and the conduct expectations live in `CODE_OF_CONDUCT.md`.

## Setup

The application is the Python package in `app/` (Python ≥ 3.12):

```sh
cd app
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev,web]'
```

Run the web shell:

```sh
uvicorn chemica.web.main:app --port 8802
```

Then open `http://localhost:8802` — search a compound, get a dossier page.

## Tests

```sh
cd app
pytest
ruff check src tests    # lint gate — config in app/pyproject.toml
```

Tests replay recorded HTTP fixtures and never touch the network. The seam is
`app/tests/conftest.py`: each source's HTTP call is monkeypatched to read the
matching file under `app/tests/fixtures/`.

When a source's API shape changes (or you add a new endpoint), record fresh
fixtures once, with network:

```sh
cd app
python -m chemica.fixtures record <compound-name>
```

`app/src/chemica/fixtures.py` snapshots raw per-endpoint responses — not shaped
payloads — so replay sees exactly what the live API returned.

## Architecture

- `app/src/chemica/core.py` — the compound/page model and the composer that
  merges sources. Independent of the web layer; nothing here imports FastAPI.
- `app/src/chemica/sources/` — one adapter per upstream (PubChem, Wikipedia /
  MediaWiki, PsychonautWiki, PubMed). Each returns plain model objects.
- `app/src/chemica/web/` — FastAPI routes, Jinja templates, static assets.
  Presentation only.
- `app/src/chemica/crossrefs.py` — Wikipedia-outlink candidate extraction for
  the related-compounds rail.
- `app/src/chemica/cache.py` — the disk cache that keeps warm loads fast.

### Deferred fragments

Slow secondary panels (references, related compounds, hazards, interactions)
do not block first paint. The page route renders the core dossier; each panel
is a `<div class="fragment-slot">` that `static/fragments.js` swaps for a
rendered partial from a `/compound/{name}/<panel>` route. When all slots
settle, the script sets `data-panels-settled="1"` on `<body>` — tests and
browser checks should wait on that signal, not on timing.

Anchor IDs belong on the *rendered* section inside the partial, not on the
slot — `outerHTML` replacement deletes the slot node.

### Vendored assets

Third-party browser assets are vendored under `app/src/chemica/web/static/`
rather than loaded from a CDN: `3dmol-min.js` (BSD-3, see
`3DMOL-LICENSE`) and the GHS pictogram SVGs (UN GHS standard images). Keep it
that way — no runtime external script/img dependencies.

## Conventions

- Follow PEP 8-ish Python; keep lines under ~120 characters.
- Keep the core↔web boundary clean: sources return models, templates render
  them. No HTTP fetching in templates, no HTML in sources.
- Every panel renders a source tag (PubChem, Wikipedia, PsychonautWiki,
  PubMed). New content must carry its attribution.
- Missing data is a decline message, not an empty panel or a silent 204 —
  the TOC link stays valid either way.
- Commits are small, coherent, subject-only (imperative, under ~72 chars) —
  no trailers, no generated-by lines. Stage only your files; never
  `git add -A` over the shared tree.

## The team process

Three agent seats work this tree concurrently as a scrum team — see
`AGENTS.md` and `.devin/skills/chemica-scrum/`. If you're a human contributor
you can ignore most of that, but two rules are load-bearing for everyone:

- One writer per file at a time — announce before editing a file a teammate
  is working in.
- An honest "I could not verify this" beats a confident guess. Run the suite
  before claiming a change works.
