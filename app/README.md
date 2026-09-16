# chemica (Python package)

The Python implementation of Chemica — a compound-reference web app that turns a substance
name into a sourced dossier from PubChem, Wikipedia, PsychonautWiki, and PubMed.

See the [repository README](../README.md) for features, architecture, and licensing.

## Quickstart

```sh
pip install -e ".[dev,web]"
uvicorn chemica.web.main:app --port 8802
pytest          # offline, fixture-backed
```
