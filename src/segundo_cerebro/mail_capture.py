"""Captura manual de un correo a la memoria.

Es el ÚNICO camino por el que texto de correo entra al cerebro, y siempre
por acción explícita tuya (un clic o `sb mail capture <id>`). El triaje
sigue sin persistir correos. El texto capturado se guarda como nota local
en .brain/captured/ y pasa por la misma capa cognitiva que cualquier
documento (heurística; Claude solo si el área está habilitada).
"""

from __future__ import annotations

import re
from pathlib import Path

from .models import Document, new_id

SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, limit: int = 48) -> str:
    text = (text or "correo").lower()
    text = (text.replace("á", "a").replace("é", "e").replace("í", "i")
                .replace("ó", "o").replace("ú", "u").replace("ñ", "n"))
    return SLUG_RE.sub("-", text).strip("-")[:limit] or "correo"


def email_to_note(email: dict) -> str:
    """Markdown con frontmatter, en el mismo formato del vault."""
    day = (email.get("date") or "")[:10]
    lines = ["---", f'title: "{(email.get("subject") or "(sin asunto)").replace(chr(34), "")}"',
             f"date: {day}", "type: email",
             f'from: "{(email.get("from") or "").replace(chr(34), "")}"',
             f'to: "{(email.get("to") or "").replace(chr(34), "")}"',
             f"account: {email.get('account', '')}",
             f"message_id: {email.get('id', '')}", "---", "",
             f"# {email.get('subject') or '(sin asunto)'}", "",
             f"De: {email.get('from', '')}", f"Fecha: {email.get('date', '')}", "",
             (email.get("body") or email.get("snippet") or "").strip()]
    return "\n".join(lines)


def capture_email(store, brain_dir: str | Path, email: dict,
                  prefer_llm: bool = False) -> dict:
    from .areas import assign_all, load_areas
    from .extract import HeuristicExtractor, get_extractor
    from .ingest import new_summary, process_document

    captured = Path(brain_dir) / "captured"
    captured.mkdir(parents=True, exist_ok=True)
    day = (email.get("date") or "")[:10] or "sin-fecha"
    path = captured / f"{day}-{slugify(email.get('subject', ''))}.md"
    n = 1
    while path.exists() and path.read_text(encoding="utf-8").find(
            f"message_id: {email.get('id', '')}") < 0:
        path = captured / f"{day}-{slugify(email.get('subject', ''))}-{n}.md"
        n += 1
    note = email_to_note(email)
    path.write_text(note, encoding="utf-8")

    body = (email.get("body") or email.get("snippet") or "").strip()
    doc = Document(
        id=new_id("doc"), path=str(path), title=email.get("subject") or "(sin asunto)",
        doc_type="email", date=day if day != "sin-fecha" else "1970-01-01",
        body=f"De: {email.get('from', '')}\n\n{body}",
        metadata={"source": "gmail-capture", "account": email.get("account", ""),
                  "from": email.get("from", ""), "message_id": email.get("id", ""),
                  "people": [_sender(email.get("from", ""))]},
    )
    if not store.add_document(doc):
        return {"duplicate": True, "path": str(path)}
    extractor = get_extractor(prefer_llm=prefer_llm) if prefer_llm else HeuristicExtractor()
    summary = new_summary(extractor)
    process_document(store, doc, extractor, summary)
    areas = load_areas()
    if areas:
        assign_all(store, areas)
        doc = store.get_document(doc.id)
    return {"duplicate": False, "path": str(path), "doc_id": doc.id,
            "area": doc.area, "kos": summary["knowledge_objects"], "title": doc.title}


def capture_by_id(store, brain_dir: str | Path, alias: str, message_id: str,
                  fetch=None, prefer_llm: bool = False) -> dict:
    """Trae UN correo (cuerpo incluido) bajo acción explícita y lo captura."""
    if fetch is None:
        from .connectors.gmail import fetch_message
        base = Path(brain_dir) / "google"
        fetch = lambda a, m: fetch_message(a, m, base=base)
    email = fetch(alias, message_id)
    if not email:
        return {"error": f"no encontré el mensaje {message_id} en «{alias}»"}
    email.setdefault("account", alias)
    return capture_email(store, brain_dir, email, prefer_llm=prefer_llm)


def _sender(from_header: str) -> str:
    head = from_header.split("<")[0].strip().strip('"')
    return head or from_header.split("@")[0]
