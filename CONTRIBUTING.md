# Contributing

## Setup

```sh
cd app
python -m venv .venv
.venv/bin/pip install -e '.[dev,web]'
```

## Verify

Run before claiming a change works — say plainly when something couldn't be
checked:

```sh
cd app
.venv/bin/pytest        # fixture-backed suite; no network required
ruff check src tests    # lint gate (config in app/pyproject.toml)
```

The web app runs with:

```sh
.venv/bin/python -m uvicorn chemica.web.main:app --port 8802
```

## Conventions

- Commit messages: short single-line imperative subjects, no bodies or
  trailers.
- Small coherent commits; stage only the files in the change.
- Source modules live under `app/src/chemica/sources/`; the web shell stays
  thin — page composition belongs in `chemica.core`.
- Missing source data renders as an honest decline, never fake empty content.
- Tests replay recorded fixtures from `app/tests/fixtures/`; record new
  fixtures for new endpoints rather than hitting the network in tests.
- Maximum line length 120.

This project follows the Contributor Covenant; see CODE_OF_CONDUCT.md.
