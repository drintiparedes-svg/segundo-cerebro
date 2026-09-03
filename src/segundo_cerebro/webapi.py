"""Lógica de la API web, compartida por los transportes del servidor.

`sb serve` la usa sobre la memoria viva (SQLite) o sobre un snapshot de
solo lectura: una sola definición de las rutas.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

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


def areas_payload(store, params: dict) -> list:
    """Áreas de trabajo con sus conteos. El mapa se lee del vault local."""
    from .areas import load_areas
    if store is None:
        return []
    counts = store.area_counts()
    out = []
    for area in load_areas():
        c = counts.get(area.id, {})
        out.append({
            "id": area.id, "name": area.name,
            "documents": c.get("documents", 0), "kos": c.get("kos", 0),
            "tasks_open": c.get("tasks_open", 0),
            "decisions": c.get("decisions", 0),
            "people": area.people, "projects": area.projects,
        })
    sin = counts.get("_sin_area", {})
    if sin.get("documents") or sin.get("kos"):
        out.append({"id": "_sin_area", "name": "Sin área",
                    "documents": sin.get("documents", 0), "kos": sin.get("kos", 0),
                    "tasks_open": sin.get("tasks_open", 0),
                    "decisions": sin.get("decisions", 0),
                    "people": [], "projects": []})
    return out


def mail_payload(store, params: dict) -> list:
    """Último triaje de correo generado por `sb agent mail`. Solo metadatos
    (remitente, asunto, prioridad, razones); nunca cuerpos."""
    db_path = getattr(store, "db_path", None)
    if not db_path:
        return []
    latest = Path(db_path).parent / "reports" / "latest-triage.json"
    if latest.exists():
        return json.loads(latest.read_text(encoding="utf-8"))
    return []


ROUTES = {
    "/api/graph": lambda store, params: graph_payload(store),
    "/api/kos": kos_payload,
    "/api/search": search_payload,
    "/api/context": context_payload,
    "/api/mail": mail_payload,
    "/api/areas": areas_payload,
}


def dispatch(store, path: str, params: dict) -> tuple[int, object]:
    handler = ROUTES.get(path)
    if not handler:
        return 404, {"error": "not found"}
    return 200, handler(store, params)


def json_bytes(payload) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")
