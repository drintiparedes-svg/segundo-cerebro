"""Agente curador: agrupa todos los documentos de la memoria en colecciones.

Dos modos:
- Claude: clasificación semántica por proyecto/tema (solo viajan título,
  ruta y un extracto corto de cada documento, nunca el contenido íntegro).
- Heurístico (100% local): agrupa por fuente y carpeta de origen.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

from ..models import new_id, now_iso
from .. import extract as _extract

EXCERPT_CHARS = 240
MAX_DOCS = 400


def _doc_digest(doc) -> dict:
    return {
        "id": doc.id,
        "title": doc.title,
        "path": doc.path,
        "type": doc.doc_type,
        "date": doc.date,
        "excerpt": doc.body[:EXCERPT_CHARS],
    }


def heuristic_grouping(documents) -> list[dict]:
    """Agrupa por origen: alias de la fuente local, cuenta Google o carpeta."""
    groups: dict[str, list] = defaultdict(list)
    for doc in documents:
        meta = doc.metadata
        if meta.get("source_alias"):
            key = meta["source_alias"]
        elif meta.get("source") == "google-calendar":
            key = f"Calendario ({meta.get('account', '?')})"
        elif meta.get("source") == "google-drive":
            key = f"Drive ({meta.get('account', '?')})"
        elif doc.path.startswith("brain"):
            key = "Vault"
        else:
            parent = Path(doc.path).parent.name
            key = parent or "Sin clasificar"
        groups[key].append(doc.id)
    return [
        {"id": new_id("col"), "name": name, "doc_ids": ids,
         "rationale": "agrupado por carpeta/fuente de origen",
         "created_at": now_iso()}
        for name, ids in sorted(groups.items())
    ]


CLAUDE_PROMPT = """Eres el agente curador de un segundo cerebro personal.
Recibes el catálogo de documentos (título, ruta, tipo, fecha y un extracto
corto). Agrúpalos en colecciones coherentes por proyecto o tema (no por
formato de archivo). Devuelve SOLO JSON:

{"collections": [
  {"name": "…", "rationale": "una frase con el criterio",
   "doc_ids": ["…"]}
]}

Reglas: entre 3 y 12 colecciones; cada documento va en exactamente una;
usa nombres cortos y reconocibles; si algo no calza, colección «Por revisar»."""


def claude_grouping(documents) -> list[dict]:
    import anthropic

    digests = [_doc_digest(d) for d in documents[:MAX_DOCS]]
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=os.environ.get("SB_MODEL", "claude-opus-5"),
        max_tokens=16000,
        system=[{"type": "text", "text": CLAUDE_PROMPT,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user",
                   "content": json.dumps(digests, ensure_ascii=False)}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    payload = json.loads(_extract._strip_fences(text))
    valid_ids = {d.id for d in documents}
    collections = []
    for col in payload.get("collections", []):
        doc_ids = [i for i in col.get("doc_ids", []) if i in valid_ids]
        if doc_ids:
            collections.append({
                "id": new_id("col"), "name": col.get("name", "Sin nombre"),
                "rationale": col.get("rationale", ""),
                "doc_ids": doc_ids, "created_at": now_iso(),
            })
    return collections


def organize(store, prefer_llm: bool = True) -> list[dict]:
    documents = store.list_documents()
    if not documents:
        return []
    collections = None
    if prefer_llm:
        try:
            import anthropic  # noqa: F401
            collections = claude_grouping(documents)
        except Exception:
            collections = None  # sin credenciales o error → modo local
    if not collections:
        collections = heuristic_grouping(documents)
    store.replace_collections(collections)
    return collections


def to_markdown(collections, store) -> str:
    lines = ["# Colecciones del segundo cerebro", ""]
    for col in collections:
        lines.append(f"## {col['name']} ({len(col['doc_ids'])})")
        if col.get("rationale"):
            lines.append(f"_{col['rationale']}_")
        for doc_id in col["doc_ids"]:
            doc = store.get_document(doc_id)
            if doc:
                lines.append(f"- {doc.date} · {doc.title} ({doc.path})")
        lines.append("")
    return "\n".join(lines)
