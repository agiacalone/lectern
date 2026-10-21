"""Canvas LMS REST client — the only module that holds a Canvas token.

Lectern talks to Canvas with one personal access token per instructor. The
token carries that instructor's full permissions and cannot be scoped, so this
module is deliberately narrow about where it goes:

- **Read from a file, never from argv or the environment.** The default path
  is ``~/.config/lectern/canvas-token``; ``LECTERN_CANVAS_TOKEN_FILE`` may point
  elsewhere. The file must be owned by the caller and unreadable by group and
  other (the ``ssh`` rule), or the client refuses to start.
- **Sent only to the configured Canvas host.** Redirects are refused rather
  than followed, because urllib forwards the ``Authorization`` header to
  whatever host a redirect names. Pagination links on another host are refused
  the same way.
- **Never printed.** No message, exception or log line this module produces
  contains the token; :func:`_scrub` removes it from anything Canvas echoes back.

The client is stdlib-only (``urllib``) to keep lectern's runtime dependencies
at ``pyyaml`` + ``jsonschema``. Tests inject a fake ``transport``.

Config (``~/.config/lectern/config.toml``)::

    [canvas]
    base_url = "https://csulb.instructure.com"   # default

``LECTERN_CANVAS_URL`` overrides the config file.
"""
from __future__ import annotations

import json
import os
import re
import stat
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

DEFAULT_BASE_URL = "https://csulb.instructure.com"
DEFAULT_TOKEN_FILE = "~/.config/lectern/canvas-token"
CONFIG = Path(os.environ.get("LECTERN_CONFIG", "~/.config/lectern/config.toml")).expanduser()

# Canvas tokens are "<account-shard digits>~<alphanumerics>".
_TOKEN_SHAPE = re.compile(r"^\d+~[A-Za-z0-9]+$")

# A transport takes (method, url, headers, body) and returns
# (status, response headers, response body).
Transport = Callable[[str, str, dict, bytes | None], tuple[int, dict, bytes]]


class CanvasError(Exception):
    """A Canvas call failed, or the client could not be configured."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


# ── configuration ────────────────────────────────────────────────────────────


def token_path() -> Path:
    """Where the token file lives (``LECTERN_CANVAS_TOKEN_FILE`` or the default)."""
    return Path(os.environ.get("LECTERN_CANVAS_TOKEN_FILE", DEFAULT_TOKEN_FILE)).expanduser()


def load_token(path: Path | None = None) -> str:
    """Read and check the token file. Raises :class:`CanvasError`, never echoing it."""
    path = path or token_path()
    try:
        st = path.stat()
    except FileNotFoundError:
        raise CanvasError(
            f"no Canvas token at {path}. Store one with a hidden prompt "
            "(read -rs) into that file, mode 600; see docs/canvas-api.md"
        ) from None
    if st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise CanvasError(
            f"{path} is readable by group or other (mode {stat.S_IMODE(st.st_mode):o}); "
            f"run: chmod 600 {path}"
        )
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        raise CanvasError(f"{path} is not owned by the current user")
    token = path.read_text(encoding="utf-8").strip()
    if not _TOKEN_SHAPE.match(token):
        raise CanvasError(
            f"{path} does not look like a Canvas token (expected digits~alphanumerics, "
            "with no quotes, spaces or 'Bearer ' prefix)"
        )
    return token


def base_url() -> str:
    """The Canvas origin: ``LECTERN_CANVAS_URL``, then ``[canvas] base_url``, then CSULB."""
    env = os.environ.get("LECTERN_CANVAS_URL")
    if env:
        return env.rstrip("/")
    if CONFIG.exists():
        try:
            cfg = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            raise CanvasError(f"{CONFIG}: {e}") from None
        url = (cfg.get("canvas") or {}).get("base_url")
        if url:
            return str(url).rstrip("/")
    return DEFAULT_BASE_URL


# ── transport ────────────────────────────────────────────────────────────────


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects: following one would forward the Authorization header."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        raise urllib.error.HTTPError(
            req.full_url, code, f"refused redirect to {newurl}", headers, fp
        )


_OPENER = urllib.request.build_opener(_NoRedirect)


def urllib_transport(method: str, url: str, headers: dict, body: bytes | None):
    """Default transport over urllib, with redirects disabled."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with _OPENER.open(req, timeout=60) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() if e.fp else b""
    except urllib.error.URLError as e:
        raise CanvasError(f"cannot reach Canvas: {e.reason}") from None


# ── client ───────────────────────────────────────────────────────────────────


_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="([a-z]+)"')


def _next_link(headers: dict) -> str | None:
    link = next((v for k, v in headers.items() if k.lower() == "link"), "")
    for url, rel in _LINK_RE.findall(link):
        if rel == "next":
            return url
    return None


@dataclass
class CanvasClient:
    """A Canvas REST client bound to one host and one token."""

    base: str
    token: str = field(repr=False)
    transport: Transport = urllib_transport
    retries: int = 3
    sleep: Callable[[float], None] = time.sleep

    @classmethod
    def from_config(cls, transport: Transport | None = None) -> "CanvasClient":
        return cls(base=base_url(), token=load_token(),
                   transport=transport or urllib_transport)

    # -- internals --

    @property
    def host(self) -> str:
        return urllib.parse.urlsplit(self.base).netloc

    def _url(self, path: str, params: dict | list | None = None) -> str:
        if path.startswith("http"):
            url = path
        else:
            url = f"{self.base}/api/v1/{path.lstrip('/')}"
        if params:
            sep = "&" if "?" in url else "?"
            url += sep + urllib.parse.urlencode(params, doseq=True)
        return url

    def _scrub(self, text: str) -> str:
        return text.replace(self.token, "[token]") if self.token else text

    def request(self, method: str, path: str, params=None, data=None, idempotent=None):
        """One call. Returns ``(parsed JSON, response headers)``.

        A dropped connection is retried for a GET, or for a write the caller
        marks ``idempotent`` (setting a grade or a like). Other writes are not
        retried: a timeout can arrive after Canvas has acted, and a second
        announcement would notify students twice.
        """
        url = self._url(path, params)
        if urllib.parse.urlsplit(url).netloc != self.host:
            raise CanvasError(f"refusing to send the token to {urllib.parse.urlsplit(url).netloc}")
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"

        safe = method == "GET" if idempotent is None else idempotent
        for attempt in range(self.retries + 1):
            try:
                status, rh, raw = self.transport(method, url, headers, body)
            except CanvasError as e:
                if e.status is None and safe and attempt < self.retries:
                    self.sleep(2 ** attempt)
                    continue
                raise
            text = raw.decode("utf-8", errors="replace")
            # Canvas throttles with 403 + "Rate Limit Exceeded"; 429 on some hosts.
            throttled = status == 429 or (status == 403 and "Rate Limit Exceeded" in text)
            if throttled and attempt < self.retries:
                self.sleep(2 ** attempt)
                continue
            break

        if status >= 400:
            raise CanvasError(f"{method} {self._display(url)}: HTTP {status}: "
                              f"{self._error_text(text)}", status)
        if not raw.strip():
            return None, rh
        try:
            return json.loads(text), rh
        except json.JSONDecodeError:
            raise CanvasError(f"{method} {self._display(url)}: non-JSON response "
                              f"(HTTP {status})", status) from None

    def _display(self, url: str) -> str:
        """The URL without host or query, for messages."""
        return urllib.parse.urlsplit(url).path

    def _error_text(self, text: str) -> str:
        try:
            doc = json.loads(text)
        except json.JSONDecodeError:
            return self._scrub(text.strip()[:200]) or "(empty body)"
        if isinstance(doc, dict):
            errs = doc.get("errors")
            if isinstance(errs, list):
                return self._scrub("; ".join(str(e.get("message", e)) if isinstance(e, dict)
                                             else str(e) for e in errs))
            if errs:
                return self._scrub(json.dumps(errs)[:300])
            if doc.get("message"):
                return self._scrub(str(doc["message"]))
        return self._scrub(text.strip()[:200])

    # -- public verbs --

    def get(self, path: str, params=None):
        return self.request("GET", path, params)[0]

    def get_all(self, path: str, params=None) -> Iterator[dict]:
        """Yield every item of a paginated list, following ``rel="next"``."""
        params = list(params.items()) if isinstance(params, dict) else list(params or [])
        if not any(k == "per_page" for k, _ in params):
            params.append(("per_page", 100))
        page, headers = self.request("GET", path, params)
        while True:
            yield from page or []
            nxt = _next_link(headers)
            if not nxt:
                return
            page, headers = self.request("GET", nxt)

    def post(self, path: str, data: dict, idempotent: bool = False):
        return self.request("POST", path, data=data, idempotent=idempotent)[0]

    def put(self, path: str, data: dict, idempotent: bool = False):
        return self.request("PUT", path, data=data, idempotent=idempotent)[0]

    def wait_progress(self, progress: dict, timeout: float = 120.0) -> dict:
        """Poll a Canvas Progress object until it completes or fails."""
        url = progress.get("url") or f"progress/{progress['id']}"
        waited = 0.0
        while True:
            state = progress.get("workflow_state")
            if state == "completed":
                return progress
            if state == "failed":
                raise CanvasError(f"Canvas job failed: {progress.get('message') or 'no message'}")
            if waited >= timeout:
                raise CanvasError(f"Canvas job still {state} after {timeout:.0f}s; "
                                  f"check progress {progress.get('id')}")
            self.sleep(1.0)
            waited += 1.0
            progress = self.get(url)
