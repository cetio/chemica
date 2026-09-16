# Chemica

[![License](https://img.shields.io/badge/License-AGPL--3-blue)](LICENSE.txt)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](app/pyproject.toml)

Chemica is a compound-reference web app: give it a substance name and it assembles a sourced dossier —
properties and identifiers from PubChem, the article from Wikipedia, dosage, effects, and interaction
data from PsychonautWiki, literature references from PubMed, and GHS hazard pictograms from PubChem's
safety record — rendered as a single readable page with a live 3D structure viewer.

https://github.com/user-attachments/assets/33b72559-45b5-4a8c-ad70-571d5741e524

## Features

- **3D molecular viewer** — PubChem 3D conformers rendered with 3Dmol.js, with atom tooltips and a
  2D fallback.
- **Chemical properties and identifiers** — XLogP, MW, formula, TPSA, charge, SMILES, InChI,
  InChIKey, CAS.
- **Dosage tables** — per-route thresholds and dose ranges plus bioavailability, from
  PsychonautWiki's SubstanceBox.
- **Effects timelines** — onset / come-up / peak / offset / after-effects per route.
- **Interactions** — dangerous and uncertain combination warnings with descriptions.
- **GHS hazards** — pictograms, signal word, and H-statements from PubChem's safety section.
- **Literature references** — PubMed search results linked per paper.
- **Cross-references** — related compounds resolved and linked, including curated "See also" entries.
- **Progressive rendering** — PubChem, Wikipedia, and PsychonautWiki fetch in parallel for first
  paint; heavier panels (interactions, references, hazards, cross-references) load as lazy fragments.
- **Persistent HTTP cache** — upstream responses are cached on disk, so warm loads are near-instant
  and survive restarts.

### Sources

- **PubChem** — compound resolution, properties, identifiers, 2D/3D structures, GHS safety data.
- **Wikipedia** — article prose and section structure.
- **PsychonautWiki** — dosage, duration, bioavailability, and interaction data via the MediaWiki API.
- **PubMed** — literature references via NCBI Entrez.

## Running

```sh
cd app
pip install -e ".[web]"
uvicorn chemica.web.main:app --port 8802
```

Then open <http://127.0.0.1:8802> and search for a compound.

## Testing

```sh
cd app
pip install -e ".[dev,web]"
pytest
```

Tests run entirely offline against recorded API fixtures (`tests/fixtures/`). New fixtures can be
captured with the recorders in `src/chemica/fixtures.py`.

## Architecture

The Python package lives under `app/src/chemica/`:

- `web/main.py` — FastAPI routes: the compound page plus lazy fragment endpoints.
- `web/templates/`, `web/static/` — Jinja2 templates, styles, and front-end JavaScript.
- `sources/` — one module per upstream API (`pubchem`, `wikipedia`, `psychonaut`, `pubmed`) with
  shared MediaWiki helpers in `mediawiki.py`.
- `core.py` — composes sources into a `CompoundPage`: parallel first-paint fetch, per-source error
  isolation, and deferred panel loading.
- `crossrefs.py` — related-compound resolution, batched to stay off the request path.
- `cache.py` — persistent disk cache for upstream HTTP responses.

The legacy D/GTK desktop client remains under `source/` for reference; it is not built.

## License

Chemica is licensed under the [AGPL-3.0 license](LICENSE.txt). Third-party assets and their
attribution are recorded in [NOTICE](NOTICE) — including the vendored 3Dmol.js viewer
(BSD-3-Clause, `app/src/chemica/web/static/3Dmol-LICENSE.txt`) and the UNECE GHS pictograms.
