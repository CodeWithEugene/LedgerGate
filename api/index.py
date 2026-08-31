"""Vercel Python entry. Same routes as `python -m ledgergate.webapi`."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ledgergate.webapi import POLICIES, dispatch, get_session  # noqa: E402

for _split in ("holdout", "dev"):
    for _policy in POLICIES:
        get_session(_split, _policy)


def _original_path(raw: str) -> str:
    """Undo the rewrite that funnels every /api/* into this function."""
    parsed = urlparse(raw)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    rest = (qs.pop("p", [None]) or [None])[0]
    if not rest:
        return raw
    path = "/api/" + rest.lstrip("/")
    leftover = urlencode(qs, doseq=True)
    return f"{path}?{leftover}" if leftover else path


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):  # noqa: N802
        self._send(200, {})

    def do_GET(self):  # noqa: N802
        status, payload = dispatch("GET", _original_path(self.path))
        self._send(status, payload)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self._send(400, {"error": "request body was not valid JSON"})
            return
        status, payload = dispatch("POST", _original_path(self.path), body)
        self._send(status, payload)

    def _send(self, status: int, payload: object) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A003
        return
