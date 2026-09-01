"""Capa de captura: archivos Markdown (con frontmatter YAML) → memoria.

En V1 la fuente principal es el vault Markdown (`brain/`). Conectores de
Gmail, Calendar, Drive y transcripciones llegan en V2 como productores del
mismo tipo de Document.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

import yaml

from .extract import get_extractor
from .models import Document, Entity, Relationship, new_id
from .store import BrainStore

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_markdown(path: Path) -> Document:
    raw = path.read_text(encoding="utf-8")
    meta: dict = {}
    body = raw
    m = FRONTMATTER_RE.match(raw)
    if m:
        try:
            meta = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            meta = {}
        meta = _json_safe(meta)
        body = raw[m.end():]

    title = meta.get("title")
    if not title:
        h1 = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        title = h1.group(1).strip() if h1 else path.stem

    doc_date = str(meta.get("date") or date.today().isoformat())
    doc_type = str(meta.get("type") or _infer_type(path))

    return Document(
        id=new_id("doc"), path=str(path), title=str(title),
        doc_type=doc_type, date=doc_date, body=body.strip(), metadata=meta,
    )


def _json_safe(value):
    """YAML produce date/datetime; la memoria guarda metadatos como JSON."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _infer_type(path: Path) -> str:
    parts = {p.lower() for p in path.parts}
    if "meetings" in parts:
        return "meeting"
    if "decisions" in parts:
        return "decision"
    if "papers" in parts or "research" in parts:
        return "paper"
    return "note"


def ingest_path(store: BrainStore, target: Path, prefer_llm: bool = True) -> dict:
    """Ingesta un archivo o directorio de Markdown. Devuelve un resumen."""
    files = sorted(target.rglob("*.md")) if target.is_dir() else [target]
    extractor = get_extractor(prefer_llm=prefer_llm)
    summary = {"documents": 0, "skipped": 0, "knowledge_objects": 0,
               "entities": 0, "relationships": 0, "extractor": type(extractor).__name__}

    for f in files:
        if f.name.startswith(("_", ".")) or f.name == "README.md" or "templates" in f.parts:
            continue
        doc = parse_markdown(f)
        if not store.add_document(doc):
            summary["skipped"] += 1
            continue
        summary["documents"] += 1

        result = extractor.extract(doc)

        # Deduplicar entidades contra la memoria y reconstruir referencias.
        id_map: dict[str, str] = {}
        for ent in result.entities:
            stored = store.upsert_entity(ent)
            id_map[ent.id] = stored.id
            summary["entities"] += 1

        for ko in result.knowledge_objects:
            store.add_knowledge_object(ko)
            summary["knowledge_objects"] += 1

        for rel in result.relationships:
            rel.source_id = id_map.get(rel.source_id, rel.source_id)
            rel.target_id = id_map.get(rel.target_id, rel.target_id)
            store.add_relationship(rel)
            summary["relationships"] += 1

        # Relaciones implícitas del frontmatter: personas ↔ proyecto.
        _link_frontmatter(store, doc)

    return summary


def _link_frontmatter(store: BrainStore, doc: Document) -> None:
    meta = doc.metadata
    project_name = meta.get("project")
    people = meta.get("people") or []
    if isinstance(people, str):
        people = [p.strip() for p in people.split(",") if p.strip()]
    if not project_name:
        return
    project = store.upsert_entity(
        Entity(id=new_id("ent"), name=str(project_name), entity_type="project")
    )
    for person_name in people:
        person = store.upsert_entity(
            Entity(id=new_id("ent"), name=str(person_name), entity_type="person")
        )
        store.add_relationship(Relationship(
            id=new_id("rel"), source_id=person.id, target_id=project.id,
            rel_type="participates_in", valid_from=doc.date, source_doc=doc.id,
        ))
