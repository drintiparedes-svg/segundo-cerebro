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

    # Decisiones como nodos del mapa mental: conectadas a sus personas y
    # proyecto, y encadenadas cronológicamente dentro de cada proyecto.
    by_name = {}
    for e in entities:
        by_name.setdefault(e.name.lower(), e.id)
    decisions = sorted(
        store.list_knowledge_objects(ko_type="decision", limit=60),
        key=lambda k: k.date)
    prev_in_project: dict = {}
    for ko in decisions:
        label = ko.title if len(ko.title) <= 46 else ko.title[:44] + "…"
        node = {"id": ko.id, "name": label, "type": "decision",
                "degree": 1, "date": ko.date}
        nodes.append(node)
        for person in ko.people:
            pid = by_name.get(person.lower())
            if pid:
                links.append({"source": pid, "target": ko.id,
                              "type": "decided", "valid_from": ko.date,
                              "valid_to": None})
                node["degree"] += 1
        if ko.project:
            proj_id = by_name.get(ko.project.lower())
            if proj_id:
                links.append({"source": ko.id, "target": proj_id,
                              "type": "shapes", "valid_from": ko.date,
                              "valid_to": None})
            prev = prev_in_project.get(ko.project)
            if prev:
                links.append({"source": prev, "target": ko.id,
                              "type": "precedes", "valid_from": ko.date,
                              "valid_to": None})
            prev_in_project[ko.project] = ko.id
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
    """Áreas rankeadas por prioridad (automática × validación manual)."""
    from .areas import load_areas
    from .priority import area_scores, signals_label
    if store is None:
        return []
    counts = store.area_counts()
    brain_dir = Path(getattr(store, "db_path", Path(".brain/brain.db"))).parent
    out = []
    for row in area_scores(store, load_areas(), brain_dir):
        c = counts.get(row["id"], {})
        out.append({
            **row,
            "signals_label": signals_label(row["signals"]),
            "documents": c.get("documents", 0), "kos": c.get("kos", 0),
            "tasks_open": c.get("tasks_open", 0),
            "decisions": c.get("decisions", 0),
        })
    return out


def doc_payload(store, params: dict) -> dict:
    """Documento fuente completo, para 'ver la fuente' desde la UI."""
    doc_id = params.get("id", "")
    if store is None or not doc_id:
        return {"found": False}
    doc = store.get_document(doc_id)
    if doc is None:
        return {"found": False}
    meta = doc.metadata or {}
    link = meta.get("web_link") or meta.get("html_link") or (
        f"https://doi.org/{meta['doi']}" if meta.get("doi") else None)
    return {"found": True, "id": doc.id, "title": doc.title, "date": doc.date,
            "doc_type": doc.doc_type, "path": doc.path, "area": doc.area,
            "body": doc.body[:60_000], "web_link": link}


def why_payload(store, params: dict) -> dict:
    """Dossier de una decisión: por qué se tomó. 100% local."""
    from .areas import load_areas
    from .why import build_dossier, to_markdown
    q = params.get("q", "")
    if store is None or not q:
        return {"markdown": "Sin memoria o sin consulta.", "found": False}
    dossier = build_dossier(store, q)
    if dossier is None:
        return {"markdown": f"No encontré una decisión que calce con «{q}».",
                "found": False}
    names = {a.id: a.name for a in load_areas()}
    return {"markdown": to_markdown(dossier, names), "found": True,
            "decision": dossier["decision"]}


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
    "/api/why": why_payload,
    "/api/doc": doc_payload,
}


def dispatch(store, path: str, params: dict) -> tuple[int, object]:
    handler = ROUTES.get(path)
    if not handler:
        return 404, {"error": "not found"}
    return 200, handler(store, params)


# ── rutas POST (solo servidor local) ──────────────────────────────────────

def override_area(store, params: dict, body: bytes) -> tuple[int, object]:
    from .priority import set_override
    try:
        data = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return 400, {"error": "JSON inválido"}
    area_id = data.get("id")
    if not area_id:
        return 400, {"error": "falta id de área"}
    brain_dir = Path(getattr(store, "db_path", Path(".brain/brain.db"))).parent
    entry = set_override(
        brain_dir, area_id,
        weight=data.get("weight"), pin=data.get("pin"),
        unpin=bool(data.get("unpin")), status=data.get("status"),
    )
    return 200, {"id": area_id, "override": entry,
                 "areas": areas_payload(store, {})}


def upload_document(store, params: dict, body: bytes) -> tuple[int, object]:
    """Subida manual: guarda el archivo en .brain/uploads/, lo parsea con los
    lectores locales, lo ingesta y lo clasifica. Todo en la máquina local."""
    from .areas import load_areas
    from .connectors.localfs import file_to_document, read_file_text
    from .extract import HeuristicExtractor
    from .ingest import new_summary, process_document
    from .areas import assign_all

    filename = Path(params.get("filename", "documento.txt")).name
    if not filename or not body:
        return 400, {"error": "falta archivo o nombre (header X-Filename)"}
    brain_dir = Path(getattr(store, "db_path", Path(".brain/brain.db"))).parent
    uploads = brain_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    dest = uploads / filename
    n = 1
    while dest.exists():
        dest = uploads / f"{Path(filename).stem}-{n}{Path(filename).suffix}"
        n += 1
    dest.write_bytes(body)

    text = read_file_text(dest)
    if text is None or not text.strip():
        return 415, {"error": f"formato no soportado o vacío: {dest.suffix}"}
    doc = file_to_document(dest, "subida-manual", text)
    if not store.add_document(doc):
        return 200, {"duplicate": True,
                     "message": "El documento ya estaba en la memoria."}
    summary = new_summary(HeuristicExtractor())
    process_document(store, doc, HeuristicExtractor(), summary)
    areas = load_areas()
    if areas:
        assign_all(store, areas)
        doc = store.get_document(doc.id)
    return 200, {"title": doc.title, "area": doc.area, "path": str(dest),
                 "kos": summary["knowledge_objects"]}


POST_ROUTES = {
    "/api/areas/override": override_area,
    "/api/upload": upload_document,
}


def dispatch_post(store, path: str, params: dict, body: bytes) -> tuple[int, object]:
    handler = POST_ROUTES.get(path)
    if not handler:
        return 404, {"error": "not found"}
    if store is None:
        return 503, {"error": "sin memoria activa"}
    return handler(store, params, body)


def json_bytes(payload) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")
