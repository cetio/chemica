# Chemica

[![License](https://img.shields.io/badge/License-AGPL--3-blue)](LICENSE.txt)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](app/pyproject.toml)

Chemica is a compound-reference web app. It turns a substance name into a sourced
article assembled from PubChem, Wikipedia, PsychonautWiki, and PubMed.

The project was rewritten in September 2026 as a Python web application. The
original GTK D implementation is preserved at commit
4199083a6220ca2152940c661c190dd5ed00484c and is no longer maintained.

## Features

- **3D molecular viewer**: PubChem 3D conformers rendered with 3Dmol.js, with atom
  tooltips and a 2D fallback.
- **Chemical properties and identifiers**: XLogP, MW, formula, TPSA, charge,
  SMILES, InChI, InChIKey, and CAS.
- **Dosage tables**: per-route thresholds and dose ranges, plus bioavailability,
  from PsychonautWiki's SubstanceBox.
- **Effect timelines**: onset, come-up, peak, offset, and after-effects per route.
- **Interactions**: dangerous and uncertain combination warnings with descriptions.
- **GHS hazards**: pictograms, signal word, and H-statements from PubChem's safety
  section.
- **Literature references**: PubMed search results linked per paper.
- **Cross-references**: related compounds resolved and linked, including curated
  "See also" entries.
- **Progressive rendering**: PubChem, Wikipedia, and PsychonautWiki fetch in
  parallel for first paint; interactions, references, hazards, and cross-references
  load as deferred fragments.
- **Persistent HTTP cache**: upstream responses are cached on disk, so warm loads
  are near-instant and survive restarts.

## Sources

| Source | Data |
| --- | --- |
| PubChem | Compound resolution, properties, identifiers, 2D/3D structures, and GHS safety data. |
| Wikipedia | Article prose and section structure. |
| PsychonautWiki | Dosage, duration, bioavailability, and interaction data via the MediaWiki API. |
| PubMed | Literature references via NCBI Entrez. |

## Running

```sh
cd app
pip install -e ".[web]"
uvicorn chemica.web.main:app --port 8802
```

Open <http://127.0.0.1:8802> and search for a compound.

## Testing

```sh
cd app
pip install -e ".[dev,web]"
pytest
```

Tests run entirely offline against recorded API fixtures (`app/tests/fixtures/`).
New fixtures are captured with the recorders in `app/src/chemica/fixtures.py`.

## Architecture

The Python package lives under `app/src/chemica/`:

| Path | Contents |
| --- | --- |
| `web/main.py` | FastAPI routes: the compound page and the deferred fragment endpoints. |
| `web/templates/`, `web/static/` | Jinja2 templates, styles, and front-end JavaScript. |
| `sources/` | One module per upstream API (`pubchem`, `wikipedia`, `psychonaut`, `pubmed`), with shared MediaWiki helpers in `mediawiki.py`. |
| `core.py` | Composes sources into a `CompoundPage`: parallel first-paint fetch, per-source error isolation, and deferred panel loading. |
| `crossrefs.py` | Related-compound resolution, batched to stay off the request path. |
| `cache.py` | Persistent disk cache for upstream HTTP responses. |

## License

Chemica is licensed under the [AGPL-3.0 license](LICENSE.txt). Third-party assets
and their attribution are recorded in [NOTICE](NOTICE), including the vendored
3Dmol.js viewer (BSD-3-Clause,
`app/src/chemica/web/static/3Dmol-LICENSE.txt`) and the UNECE GHS pictograms.
