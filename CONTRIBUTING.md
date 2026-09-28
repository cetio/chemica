# Contributing to Chemica

Thanks for contributing to Chemica. Keep changes focused, follow the existing
design and Python style, and include tests for behavioral changes.

## Reporting Issues

Search existing issues before opening a new one. Bug reports should include:

- Steps to reproduce and the compound name that triggers the problem.
- Expected and actual behavior.
- Python version and operating system.
- Relevant client or upstream logs, without credentials or other sensitive data.

Feature requests should describe the use case, the expected page or panel
behavior, and which source the data would come from.

## Development Setup

The application is the Python package in `app/` (Python 3.12 or newer):

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

Then open <http://127.0.0.1:8802> and search for a compound.

## Pull Requests

- Work on a focused branch and explain both what changed and why.
- Follow the conventions in neighboring modules. Avoid unnecessary dependencies
  or abstractions.
- Document public types and functions with docstrings.
- Call out intentional differences from an upstream API's documented behavior.
- Update user and contributor documentation when commands or public behavior
  change.
- Add tests for every bug fix and feature.

## Tests

Run the offline suite and the linter before submitting a pull request:

```sh
cd app
pytest
ruff check src tests
```

Tests replay recorded HTTP fixtures and never touch the network. The seam is
`app/tests/conftest.py`: each source's HTTP call is monkeypatched to read the
matching file under `app/tests/fixtures/`.

When a source's API shape changes, or when you add an endpoint, record fresh
fixtures once with network access:

```sh
cd app
python -m chemica.fixtures record <compound-name>
```

`app/src/chemica/fixtures.py` snapshots raw per-endpoint responses rather than
shaped payloads, so replay sees exactly what the live API returned.

## Architecture

| Path | Contents |
| --- | --- |
| `app/src/chemica/core.py` | The compound/page model and the composer that merges sources. Independent of the web layer. |
| `app/src/chemica/sources/` | One adapter per upstream (PubChem, Wikipedia/MediaWiki, PsychonautWiki, PubMed). Each returns plain model objects. |
| `app/src/chemica/web/` | FastAPI routes, Jinja templates, and static assets. Presentation only. |
| `app/src/chemica/crossrefs.py` | Candidate extraction for the related-compounds rail. |
| `app/src/chemica/cache.py` | The disk cache that keeps warm loads fast. |

### Deferred fragments

Secondary panels (references, related compounds, hazards, interactions) do not
block first paint. The page route renders the core article; each panel is a
`<div class="fragment-slot">` that `static/fragments.js` swaps for a rendered
partial from a `/compound/{name}/<panel>` route. When all slots settle, the
script sets `data-panels-settled="1"` on `<body>`; tests and browser checks
should wait on that signal rather than on timing.

Anchor IDs belong on the rendered section inside the partial, not on the slot,
because `outerHTML` replacement deletes the slot node.

### Vendored assets

Third-party browser assets are vendored under `app/src/chemica/web/static/`
rather than loaded from a CDN: `3dmol-min.js` (BSD-3-Clause, see
`3Dmol-LICENSE.txt`) and the GHS pictogram SVGs (UN GHS standard images). Keep
them vendored; the page must not depend on external scripts or images at
runtime.

## Review Checklist

Before opening a pull request:

1. Run the offline tests and the linter.
2. Confirm new tests fail without the fix when practical.
3. Review the diff for generated files, unrelated changes, and sensitive data.
4. Verify documentation examples and links affected by the change.

## Communication and Conduct

Ask questions in issues or pull request comments, and keep discussions
respectful and constructive. The conduct expectations live in
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions are licensed under the same
[AGPL-3.0 license](LICENSE.txt) as Chemica.
