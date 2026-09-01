"""Servidor web del Segundo Cerebro (stdlib, sin dependencias).

Sirve la UI (grafo de conocimiento) y una API JSON de solo lectura sobre la
memoria. Pensado para uso local: `sb serve` y abrir http://127.0.0.1:8765.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlparse

from .context import build_context
from .store import BrainStore


def _graph_payload(store: BrainStore) -> dict:
    entities = store.list_entities()
    nodes = []
    links = []
    degree: dict[str, int] = {}
    seen_links = set()
    for ent in entities:
        for rel in store.relationships_of(ent.id):
            if rel.id in seen_links:
                continue
            seen_links.add(rel.id)
            links.append({
                "source": rel.source_id, "target": rel.target_id,
                "type": rel.rel_type, "valid_from": rel.valid_from,
                "valid_to": rel.valid_to,
            })
            degree[rel.source_id] = degree.get(rel.source_id, 0) + 1
            degree[rel.target_id] = degree.get(rel.target_id, 0) + 1
    for ent in entities:
        nodes.append({
            "id": ent.id, "name": ent.name, "type": ent.entity_type,
            "degree": degree.get(ent.id, 0),
        })
    return {"nodes": nodes, "links": links}


class BrainHandler(BaseHTTPRequestHandler):
    store: BrainStore  # inyectado por serve()

    def do_GET(self) -> None:  # noqa: N802 (nombre requerido por http.server)
        url = urlparse(self.path)
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path in ("/", "/index.html"):
                html = resources.files("segundo_cerebro.ui").joinpath("index.html").read_text("utf-8")
                # El archivo omite el esqueleto (doctype/html/head) para ser
                # publicable también como Artifact; aquí lo completamos.
                self._respond(200, "<!doctype html>\n<html lang='es'>" + html + "</html>",
                              "text/html; charset=utf-8")
            elif url.path == "/api/graph":
                self._json(_graph_payload(self.store))
            elif url.path == "/api/kos":
                kos = self.store.list_knowledge_objects(
                    ko_type=params.get("type"), status=params.get("status"),
                    limit=int(params.get("limit", 100)))
                self._json([asdict(k) for k in kos])
            elif url.path == "/api/search":
                q = params.get("q", "")
                self._json({
                    "knowledge_objects": [asdict(k) for k in self.store.search_knowledge_objects(q)],
                    "documents": [
                        {"id": d.id, "title": d.title, "date": d.date,
                         "doc_type": d.doc_type, "path": d.path}
                        for d in self.store.search_documents(q)
                    ],
                })
            elif url.path == "/api/context":
                pack = build_context(self.store, params.get("q", ""))
                self._json({"markdown": pack.to_markdown(), "intent": pack.intent})
            else:
                self._respond(404, json.dumps({"error": "not found"}), "application/json")
        except Exception as exc:  # el servidor local no debe caerse por una request
            self._respond(500, json.dumps({"error": str(exc)}), "application/json")

    def log_message(self, fmt: str, *args) -> None:
        pass  # silencioso; el CLI ya informa host/puerto

    def _json(self, payload) -> None:
        self._respond(200, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8")

    def _respond(self, status: int, body: str, content_type: str) -> None:
        data = body.encode("utf-8")
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
