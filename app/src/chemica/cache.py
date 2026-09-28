"""On-disk HTTP response cache that survives process restarts.

Sources route requests through `get` instead of `requests.get`, so a cold
process does not re-pay the network for data that has not changed. Entries are
keyed by URL and stored as JSON under `~/.cache/chemica/http/`, with binary
bodies base64-encoded alongside their Content-Type, and expire after
`_TTL_SECONDS`. Set `CHEMICA_NO_CACHE=1` to bypass the cache entirely; the test
suite does, so recorded fixtures stay authoritative over anything a live run
cached.

Writes are atomic (temporary file plus rename) and misses are single-flight, one
upstream request per URL at a time, so parallel fetches cannot leave a
half-written entry or stampede a host.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

import requests

_TTL_SECONDS = 24 * 60 * 60

_CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "chemica" / "http"

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def get(url: str, ok: Callable[[requests.Response], bool] | None = None, **kwargs) -> requests.Response:
    """Drop-in `requests.get` with a disk cache for 200 responses.

    `ok` lets a caller declare that an HTTP 200 body is still a miss, for
    example when MediaWiki returns a 'missing' page at 200. A body that fails
    `ok` is not written, and a cached entry that fails it is treated as absent
    and refetched, so semantic negatives recorded before a rule existed heal on
    the next read instead of pinning a decline until TTL.
    """
    if os.environ.get("CHEMICA_NO_CACHE"):
        return requests.get(url, **kwargs)
    path = _entry_path(url)
    cached = _read(path)
    if cached is not None and (ok is None or ok(cached)):
        return cached
    with _locks_guard:
        lock = _locks.setdefault(url, threading.Lock())
    with lock:
        try:
            cached = _read(path)  # the caller ahead of us may have filled it
            if cached is not None and (ok is None or ok(cached)):
                return cached
            resp = requests.get(url, **kwargs)
            if resp.status_code == 200 and (ok is None or ok(resp)):
                _write(path, resp)
            return resp
        finally:
            with _locks_guard:
                if _locks.get(url) is lock:
                    del _locks[url]


def _entry_path(url: str) -> Path:
    return _CACHE_DIR / f"{hashlib.sha256(url.encode()).hexdigest()}.json"


def _read(path: Path) -> requests.Response | None:
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if time.time() - entry.get("ts", 0) > _TTL_SECONDS:
        return None
    ret = requests.Response()
    ret.status_code = entry["status"]
    if "body_b64" in entry:
        ret._content = base64.b64decode(entry["body_b64"])
    else:
        ret._content = entry["body"].encode("utf-8")
    ret.url = entry["url"]
    ret.encoding = "utf-8"
    if entry.get("content_type"):
        ret.headers["Content-Type"] = entry["content_type"]
    return ret


def _write(path: Path, resp: requests.Response) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "url": resp.url,
        "status": resp.status_code,
        "content_type": resp.headers.get("Content-Type"),
        "ts": time.time(),
    }
    try:
        payload["body"] = resp.content.decode("utf-8")
    except UnicodeDecodeError:
        payload["body_b64"] = base64.b64encode(resp.content).decode("ascii")
    try:
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload))
        os.replace(tmp, path)
    except OSError:
        pass
