"""On-disk HTTP response cache — survives process restarts.

Sources route requests through `get` instead of `requests.get` so a cold
process doesn't re-pay the network for data that hasn't changed. Entries are
keyed by URL, stored as JSON under ~/.cache/chemica/http/, and expire after
_TTL_SECONDS. Set CHEMICA_NO_CACHE=1 to bypass entirely (the test suite does —
recorded fixtures must stay authoritative over anything a live run cached).

Writes are atomic (tmp file + rename) so parallel fetches can't leave a
half-written entry.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

import requests

_TTL_SECONDS = 24 * 60 * 60

_CACHE_DIR = (
    Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    / "chemica"
    / "http"
)


def get(url: str, **kwargs) -> requests.Response:
    """Drop-in requests.get with a disk cache for 200 responses."""
    if os.environ.get("CHEMICA_NO_CACHE"):
        return requests.get(url, **kwargs)
    path = _entry_path(url)
    cached = _read(path)
    if cached is not None:
        return cached
    resp = requests.get(url, **kwargs)
    if resp.status_code == 200:
        _write(path, resp)
    return resp


def _entry_path(url: str) -> Path:
    return _CACHE_DIR / f"{hashlib.sha256(url.encode()).hexdigest()}.json"


def _read(path: Path) -> requests.Response | None:
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if time.time() - entry.get("ts", 0) > _TTL_SECONDS:
        return None
    resp = requests.Response()
    resp.status_code = entry["status"]
    resp._content = entry["body"].encode("utf-8")
    resp.url = entry["url"]
    resp.encoding = "utf-8"
    return resp


def _write(path: Path, resp: requests.Response) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"url": resp.url, "status": resp.status_code, "body": resp.text, "ts": time.time()}
    try:
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload))
        os.replace(tmp, path)
    except OSError:
        pass
