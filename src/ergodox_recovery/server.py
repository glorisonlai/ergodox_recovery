"""Loopback-only guided capture UI.

The browser performs focused key capture and sends only normalized bindings.
This server never opens an input device and never accepts raw key events.
"""

from __future__ import annotations

import json
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .model import layout_payload
from .session import RecoverySession

MAX_REQUEST_BYTES = 2 * 1024 * 1024


class RecoveryHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    # The server is hard-bound to loopback in create_server(). Allow immediate
    # restart after a local UI update instead of leaving the default port held
    # by the prior connection's TCP cleanup window.
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        session_path: Path,
        session: RecoverySession,
        token: str,
    ) -> None:
        super().__init__(server_address, RecoveryRequestHandler)
        self.session_path = session_path
        self.session = session
        self.token = token
        self.session_lock = threading.Lock()


class RecoveryRequestHandler(BaseHTTPRequestHandler):
    server: RecoveryHTTPServer

    def log_message(self, format: str, *args: object) -> None:
        # Deliberately do not produce access logs while capture is in use.
        return

    def _security_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; "
            "form-action 'none'; base-uri 'none'",
        )

    def _send_bytes(self, content: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self._security_headers(content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, value: object, status: int = 200) -> None:
        content = (json.dumps(value, separators=(",", ":")) + "\n").encode()
        self._send_bytes(content, "application/json; charset=utf-8", status)

    def _authorized(self) -> bool:
        supplied = self.headers.get("X-Recovery-Token", "")
        return secrets.compare_digest(supplied, self.server.token)

    def _valid_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if origin is None:
            return True
        parsed = urlsplit(origin)
        return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}

    def _valid_host(self) -> bool:
        host = self.headers.get("Host", "")
        try:
            parsed = urlsplit(f"//{host}")
            port = parsed.port
        except ValueError:
            return False
        return parsed.hostname in {"127.0.0.1", "localhost"} and port in {
            None,
            self.server.server_port,
        }

    def do_GET(self) -> None:  # noqa: N802
        if not self._valid_host():
            self._send_json({"error": "invalid host"}, HTTPStatus.FORBIDDEN)
            return
        path = urlsplit(self.path).path
        if path == "/":
            template = files("ergodox_recovery.web").joinpath("index.html").read_text("utf-8")
            content = template.replace("__RECOVERY_TOKEN__", self.server.token).encode()
            self._send_bytes(content, "text/html; charset=utf-8")
            return
        if path in {"/app.js", "/style.css"}:
            asset_name = path.removeprefix("/")
            content = files("ergodox_recovery.web").joinpath(asset_name).read_bytes()
            media_type = (
                "text/javascript; charset=utf-8"
                if path.endswith(".js")
                else "text/css; charset=utf-8"
            )
            self._send_bytes(content, media_type)
            return
        if path == "/api/session" and self._authorized():
            with self.server.session_lock:
                self._send_json(self.server.session.to_dict())
            return
        if path == "/api/layout" and self._authorized():
            self._send_json(layout_payload())
            return
        if path.startswith("/api/"):
            self._send_json({"error": "unauthorized"}, HTTPStatus.FORBIDDEN)
            return
        self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:  # noqa: N802
        if not self._valid_host():
            self._send_json({"error": "invalid host"}, HTTPStatus.FORBIDDEN)
            return
        if urlsplit(self.path).path != "/api/session":
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        if not self._authorized() or not self._valid_origin():
            self._send_json({"error": "unauthorized"}, HTTPStatus.FORBIDDEN)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json({"error": "invalid Content-Length"}, HTTPStatus.BAD_REQUEST)
            return
        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            self._send_json(
                {"error": "request size is invalid"}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE
            )
            return
        try:
            raw = self.rfile.read(content_length)
            data: Any = json.loads(raw)
            session = RecoverySession.from_dict(data)
            with self.server.session_lock:
                session.save(self.server.session_path)
                self.server.session = session
        except (ValueError, OSError, json.JSONDecodeError) as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        self._send_json({"ok": True, "updated_at": session.updated_at})


def create_server(
    session_path: Path | str,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    token: str | None = None,
) -> RecoveryHTTPServer:
    if host != "127.0.0.1":
        raise ValueError("capture server may only bind to 127.0.0.1")
    path = Path(session_path).expanduser().resolve()
    session = RecoverySession.load(path)
    return RecoveryHTTPServer((host, port), path, session, token or secrets.token_urlsafe(32))
