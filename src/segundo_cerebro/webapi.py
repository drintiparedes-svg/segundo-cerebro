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
    pinned = set()
    db_path = getattr(store, "db_path", None)
    if db_path:
        from .people import pinned_names
        pinned = set(pinned_names(Path(db_path).parent))
    nodes = [
        {"id": e.id, "name": e.name, "type": e.entity_type,
         "degree": degree.get(e.id, 0),
         **({"pinned": True} if e.name in pinned else {})}
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


def _brain_dir(store) -> Path | None:
    db_path = getattr(store, "db_path", None)
    return Path(db_path).parent if db_path else None


def people_payload(store, params: dict) -> dict:
    """Ranking de personas + sugerencias de pin. 100% local."""
    from .people import people_scores, signals_label
    brain_dir = _brain_dir(store)
    if brain_dir is None:
        return {"people": [], "suggested": [], "unknown_senders": []}
    data = people_scores(store, brain_dir)
    for row in data["people"]:
        row["signals_label"] = signals_label(row["signals"])
    return data


def sources_payload(store, params: dict) -> dict:
    """Fuentes registradas con su estado de sincronización + ignoradas."""
    from .connectors.localfs import load_registry
    brain_dir = _brain_dir(store)
    if brain_dir is None:
        return {"sources": [], "ignored": []}
    reg = load_registry(brain_dir)
    out = []
    for s in reg["sources"]:
        st = reg["state"].get(s["path"], {})
        out.append({**s, "last_sync": st.get("last_sync"),
                    "available": Path(s["path"]).is_dir()})
    return {"sources": out, "ignored": reg.get("ignored", [])}


def sources_suggest_payload(store, params: dict) -> dict:
    """Carpetas del escritorio/estándar que conviene conectar (solo nombres
    y fechas; nunca abre archivos)."""
    from .advisor import candidate_roots, suggest_sources
    from .areas import load_areas
    from .desktop import find_desktop
    brain_dir = _brain_dir(store)
    if brain_dir is None:
        return {"suggestions": [], "roots": []}
    roots = candidate_roots(find_desktop())
    if params.get("root"):
        roots = [Path(params["root"]).expanduser()]
    return {"roots": [str(r) for r in roots],
            "suggestions": suggest_sources(brain_dir, roots, load_areas())}


def today_payload(store, params: dict) -> dict:
    from .areas import load_areas
    from .today import build_today
    brain_dir = _brain_dir(store)
    if brain_dir is None:
        return {"markdown": "Sin memoria publicada: la instancia corre en modo demo."}
    return {"markdown": build_today(store, brain_dir, load_areas())}


def week_payload(store, params: dict) -> dict:
    from .areas import load_areas
    from .projects import load_projects, week_review
    brain_dir = _brain_dir(store)
    if brain_dir is None:
        return {"markdown": "Sin memoria publicada: la instancia corre en modo demo."}
    names = {a.id: a.name for a in load_areas()}
    return {"markdown": week_review(store, brain_dir, load_projects(), names)}


def projects_payload(store, params: dict) -> list:
    from .projects import load_projects, project_status
    if store is None:
        return []
    out = []
    for p in load_projects():
        st = project_status(store, p)
        out.append({"id": p.id, "name": p.name, "area": p.area, "deadline": p.deadline,
                    "days_to_deadline": st["days_to_deadline"], "tasks": st["tasks"],
                    "done": st["done"], "overdue": len(st["overdue"]),
                    "due_soon": len(st["due_soon"]),
                    "next_milestone": ({"name": st["next_milestone"].name,
                                        "due": st["next_milestone"].due}
                                       if st["next_milestone"] else None)})
    return out


def status_payload(store, params: dict) -> dict:
    """Última sincronización, si hay una en curso, tamaño de la memoria y
    política LLM — para la cabecera de la pestaña Hoy."""
    from .refresh import status
    brain_dir = _brain_dir(store)
    if brain_dir is None:
        return {"running": False, "last": None, "minutes_ago": None,
                "counts": {}, "llm": {}, "demo": True}
    return status(store, brain_dir)


def config_payload(store, params: dict) -> dict:
    from .areas import load_areas
    from .config import load_config
    brain_dir = _brain_dir(store)
    cfg = load_config(brain_dir) if brain_dir else load_config(Path("/nonexistent"))
    return {"config": cfg, "areas": [{"id": a.id, "name": a.name} for a in load_areas()]}


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
    "/api/people": people_payload,
    "/api/sources": sources_payload,
    "/api/sources/suggest": sources_suggest_payload,
    "/api/today": today_payload,
    "/api/status": status_payload,
    "/api/week": week_payload,
    "/api/projects": projects_payload,
    "/api/config": config_payload,
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


def _json_body(body: bytes) -> dict | None:
    try:
        return json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def pin_person(store, params: dict, body: bytes) -> tuple[int, object]:
    """Fija / suelta una persona (validación manual, .brain/people_overrides.json)."""
    from .people import set_person_override
    data = _json_body(body)
    if data is None or not data.get("name"):
        return 400, {"error": "falta name"}
    brain_dir = _brain_dir(store) or Path(".brain")
    entry = set_person_override(
        brain_dir, data["name"], pin=data.get("pin"), role=data.get("role"),
        area=data.get("area"), note=data.get("note"))
    return 200, {"name": data["name"], "override": entry,
                 **people_payload(store, {})}


def apply_source(store, params: dict, body: bytes) -> tuple[int, object]:
    """Acepta (registra) o ignora una carpeta sugerida. Solo lectura sobre
    la carpeta; lo único que se escribe es .brain/sources.json."""
    from .advisor import apply_suggestion
    data = _json_body(body)
    if data is None or not data.get("path"):
        return 400, {"error": "falta path"}
    brain_dir = _brain_dir(store) or Path(".brain")
    try:
        result = apply_suggestion(brain_dir, data["path"], bool(data.get("accept")))
    except NotADirectoryError as exc:
        return 404, {"error": str(exc)}
    return 200, {**result, **sources_payload(store, {})}


_refresh_threads: dict = {}


def start_refresh(store, params: dict, body: bytes) -> tuple[int, object]:
    """Lanza `sb refresh` en un hilo (no bloquea la UI). Si ya hay uno en
    curso, lo dice sin duplicar."""
    import threading
    from .refresh import is_locked, run_refresh
    brain_dir = _brain_dir(store)
    if brain_dir is None:
        return 400, {"error": "sin memoria local (modo demo)"}
    if is_locked(brain_dir):
        return 200, {"started": False, "running": True}
    data = _json_body(body) or {}
    t = threading.Thread(target=run_refresh, args=(store, brain_dir),
                         kwargs={"skip": data.get("skip")}, daemon=True)
    t.start()
    _refresh_threads[str(brain_dir)] = t
    return 200, {"started": True, "running": True}


def set_llm_config(store, params: dict, body: bytes) -> tuple[int, object]:
    """Áreas donde se permite Claude. `never` (clinica) no se puede activar
    desde aquí: el servidor lo rechaza."""
    from .config import set_llm_areas
    data = _json_body(body)
    if data is None or not isinstance(data.get("areas"), list):
        return 400, {"error": "falta areas (lista)"}
    brain_dir = _brain_dir(store) or Path(".brain")
    try:
        cfg = set_llm_areas(brain_dir, [str(a) for a in data["areas"]])
    except ValueError as exc:
        return 403, {"error": str(exc)}
    return 200, {"config": cfg}


def capture_mail(store, params: dict, body: bytes) -> tuple[int, object]:
    """Captura manual de UN correo a la memoria (acción explícita del
    usuario). Trae el cuerpo de ese mensaje y lo guarda en .brain/captured/."""
    from .mail_capture import capture_by_id
    data = _json_body(body)
    if data is None or not data.get("id") or not data.get("account"):
        return 400, {"error": "faltan id y account"}
    brain_dir = _brain_dir(store)
    if brain_dir is None:
        return 400, {"error": "sin memoria local (modo demo)"}
    try:
        result = capture_by_id(store, brain_dir, data["account"], data["id"],
                               fetch=params.get("_fetch"))
    except Exception as exc:
        return 502, {"error": f"no pude leer el correo: {exc}"}
    if result.get("error"):
        return 404, result
    return 200, result


POST_ROUTES = {
    "/api/areas/override": override_area,
    "/api/mail/capture": capture_mail,
    "/api/refresh": start_refresh,
    "/api/config/llm": set_llm_config,
    "/api/upload": upload_document,
    "/api/people/pin": pin_person,
    "/api/sources/apply": apply_source,
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
