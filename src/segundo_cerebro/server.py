"""Servidor web local del Segundo Cerebro (stdlib, sin dependencias).

Sirve la UI y la API JSON de solo lectura sobre la memoria viva (SQLite).
Las rutas viven en webapi.py, compartidas con el despliegue serverless.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .store import BrainStore
from .ui import render_page
from .webapi import dispatch, json_bytes


class BrainHandler(BaseHTTPRequestHandler):
    store: BrainStore  # inyectado por serve()

    def do_GET(self) -> None:  # noqa: N802 (nombre requerido por http.server)
        url = urlparse(self.path)
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path in ("/", "/index.html"):
                self._respond(200, render_page().encode("utf-8"),
                              "text/html; charset=utf-8")
                return
            status, payload = dispatch(self.store, url.path, params)
            self._respond(status, json_bytes(payload),
                          "application/json; charset=utf-8")
        except Exception as exc:  # el servidor local no debe caerse por una request
            self._respond(500, json_bytes({"error": str(exc)}), "application/json")

    def log_message(self, fmt: str, *args) -> None:
        pass  # silencioso; el CLI ya informa host/puerto

    def _respond(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(store: BrainStore, host: str = "127.0.0.1", port: int = 8765) -> None:
    handler = type("Handler", (BrainHandler,), {"store": store})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Segundo Cerebro UI → http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
