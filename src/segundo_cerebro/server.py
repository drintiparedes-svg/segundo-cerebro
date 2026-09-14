"""Servidor web local del Segundo Cerebro (stdlib, sin dependencias).

Sirve la UI y la API JSON de solo lectura sobre la memoria viva (SQLite).
Las rutas viven en webapi.py, compartidas con el despliegue serverless.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .store import BrainStore
from .ui import render_page
from .webapi import dispatch, dispatch_post, json_bytes


class BrainHandler(BaseHTTPRequestHandler):
    store: BrainStore  # inyectado por serve()
    token: str | None = None   # la app de escritorio fija uno; `sb serve` no

    def _authorized(self, params: dict) -> bool:
        if not self.token:
            return True
        return (self.headers.get("X-SB-Token") == self.token
                or params.get("token") == self.token)

    def do_GET(self) -> None:  # noqa: N802 (nombre requerido por http.server)
        url = urlparse(self.path)
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if not self._authorized(params):
                self._respond(401, json_bytes({"error": "sesión no autorizada"}), "application/json")
                return
            if url.path in ("/", "/index.html"):
                self._respond(200, render_page(token=self.token).encode("utf-8"),
                              "text/html; charset=utf-8")
                return
            status, payload = dispatch(self.store, url.path, params)
            self._respond(status, json_bytes(payload),
                          "application/json; charset=utf-8")
        except Exception as exc:  # el servidor local no debe caerse por una request
            self._respond(500, json_bytes({"error": str(exc)}), "application/json")

    def do_POST(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        params["filename"] = self.headers.get("X-Filename", "")
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(min(length, 30_000_000)) if length else b""
        try:
            if not self._authorized(params):
                self._respond(401, json_bytes({"error": "sesión no autorizada"}), "application/json")
                return
            status, payload = dispatch_post(self.store, url.path, params, body)
            self._respond(status, json_bytes(payload),
                          "application/json; charset=utf-8")
        except Exception as exc:
            self._respond(500, json_bytes({"error": str(exc)}), "application/json")

    def log_message(self, fmt: str, *args) -> None:
        pass  # silencioso; el CLI ya informa host/puerto

    def _respond(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def make_server(store: BrainStore, host: str = "127.0.0.1", port: int = 8765,
                token: str | None = None) -> ThreadingHTTPServer:
    handler = type("Handler", (BrainHandler,), {"store": store, "token": token})
    return ThreadingHTTPServer((host, port), handler)


def serve(store: BrainStore, host: str = "127.0.0.1", port: int = 8765,
          token: str | None = None) -> None:
    server = make_server(store, host, port, token)
    print(f"Segundo Cerebro UI → http://{host}:{port}" + (f"/?token={token}" if token else ""))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
