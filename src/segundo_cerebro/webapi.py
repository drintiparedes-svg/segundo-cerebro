"""Lógica de la API web, compartida por los transportes del servidor.

`sb serve` la usa sobre la memoria viva (SQLite) o sobre un snapshot de
solo lectura: una sola definición de las rutas.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from .context import build_context


# ── payloads de cada ruta ─────────────────────────────────────────────────

def graph_payload(store) -> dict:
    if store is None:
        return {"nodes": [], "links": []}
    entities = store.list_entities()
    seen: set[str] = set()
    links = []
    degree: dict[str, int] = {}
    for ent in entities:
        for rel in store.relationships_of(ent.id):
            if rel.id in seen:
                continue
            seen.add(rel.id)
            links.append({
                "source": rel.source_id, "target": rel.target_id,
                "type": rel.rel_type, "valid_from": rel.valid_from,
                "valid_to": rel.valid_to,
            })
            degree[rel.source_id] = degree.get(rel.source_id, 0) + 1
            degree[rel.target_id] = degree.get(rel.target_id, 0) + 1
    nodes = [
        {"id": e.id, "name": e.name, "type": e.entity_type,
         "degree": degree.get(e.id, 0)}
        for e in entities
    ]
    return {"nodes": nodes, "links": links}


def kos_payload(store, params: dict) -> list:
    if store is None:
        return []
    kos = store.list_knowledge_objects(
        ko_type=params.get("type"), status=params.get("status"),
        limit=int(params.get("limit", 100)),
    )
    return [asdict(k) for k in kos]


def search_payload(store, params: dict) -> dict:
    if store is None:
        return {"knowledge_objects": [], "documents": []}
    q = params.get("q", "")
    return {
        "knowledge_objects": [asdict(k) for k in store.search_knowledge_objects(q)],
        "documents": [
            {"id": d.id, "title": d.title, "date": d.date,
             "doc_type": d.doc_type, "path": d.path}
            for d in store.search_documents(q)
        ],
    }


def context_payload(store, params: dict) -> dict:
    q = params.get("q", "")
    if store is None:
        return {"intent": "unavailable",
                "markdown": "Sin memoria publicada: la instancia corre en modo demo."}
    pack = build_context(store, q)
    return {"markdown": pack.to_markdown(), "intent": pack.intent}


ROUTES = {
    "/api/graph": lambda store, params: graph_payload(store),
    "/api/kos": kos_payload,
    "/api/search": search_payload,
    "/api/context": context_payload,
}


def dispatch(store, path: str, params: dict) -> tuple[int, object]:
    handler = ROUTES.get(path)
    if not handler:
        return 404, {"error": "not found"}
    return 200, handler(store, params)


def json_bytes(payload) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")
