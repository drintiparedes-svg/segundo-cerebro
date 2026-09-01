"""Snapshot de la memoria: export estático + store de solo lectura.

Permite servir el segundo cerebro desde un entorno sin disco persistente
(Vercel u otro hosting serverless): `sb export` congela la memoria en un
JSON y `SnapshotStore` expone la misma interfaz de lectura que BrainStore,
de modo que el router y el context engine funcionan sin cambios.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import Document, Entity, KnowledgeObject, Relationship, now_iso

SNAPSHOT_VERSION = 1


def export_snapshot(store, include_bodies: bool = True) -> dict:
    """Congela la memoria en una estructura JSON-serializable."""
    entities = store.list_entities()
    relationships: dict[str, Relationship] = {}
    for ent in entities:
        for rel in store.relationships_of(ent.id):
            relationships[rel.id] = rel

    degree: dict[str, int] = {}
    for rel in relationships.values():
        degree[rel.source_id] = degree.get(rel.source_id, 0) + 1
        degree[rel.target_id] = degree.get(rel.target_id, 0) + 1

    kos = store.list_knowledge_objects(limit=10_000)
    doc_ids = {ko.source_doc for ko in kos if ko.source_doc}
    documents = [d for d in (store.get_document(i) for i in doc_ids) if d]

    return {
        "version": SNAPSHOT_VERSION,
        "generated_at": now_iso(),
        "nodes": [
            {"id": e.id, "name": e.name, "type": e.entity_type,
             "degree": degree.get(e.id, 0)}
            for e in entities
        ],
        "links": [
            {"source": r.source_id, "target": r.target_id, "type": r.rel_type,
             "valid_from": r.valid_from, "valid_to": r.valid_to}
            for r in relationships.values()
        ],
        "entities": [asdict(e) for e in entities],
        "relationships": [asdict(r) for r in relationships.values()],
        "kos": [asdict(k) for k in kos],
        "documents": [
            {**asdict(d), "body": d.body if include_bodies else ""}
            for d in documents
        ],
    }


def write_snapshot(store, path: str | Path, include_bodies: bool = True) -> dict:
    data = export_snapshot(store, include_bodies=include_bodies)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


class SnapshotStore:
    """Store de solo lectura sobre un snapshot.

    Implementa la misma interfaz de lectura que BrainStore, así que
    `build_context()` y `route()` operan igual sobre él. La búsqueda usa
    coincidencia de términos en vez de FTS5 (sin dependencias, suficiente
    para el volumen de un snapshot personal).
    """

    def __init__(self, data: dict):
        self.data = data
        self._entities = [Entity(**e) for e in data.get("entities", [])]
        self._relationships = [Relationship(**r) for r in data.get("relationships", [])]
        self._kos = [KnowledgeObject(**k) for k in data.get("kos", [])]
        self._documents = [Document(**d) for d in data.get("documents", [])]
        self._by_id = {e.id: e for e in self._entities}

    @classmethod
    def from_file(cls, path: str | Path) -> "SnapshotStore":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    # ── entidades y relaciones ────────────────────────────────────────
    def list_entities(self, entity_type: str | None = None) -> list[Entity]:
        if entity_type:
            return [e for e in self._entities if e.entity_type == entity_type]
        return list(self._entities)

    def get_entity(self, entity_id: str) -> Entity | None:
        return self._by_id.get(entity_id)

    def find_entities(self, name_fragment: str) -> list[Entity]:
        frag = name_fragment.lower()
        return [
            e for e in self._entities
            if frag in e.name.lower() or any(frag in a.lower() for a in e.aliases)
        ]

    def relationships_of(self, entity_id: str) -> list[Relationship]:
        return [r for r in self._relationships
                if r.source_id == entity_id or r.target_id == entity_id]

    # ── knowledge objects y documentos ────────────────────────────────
    def list_knowledge_objects(self, ko_type=None, status=None, person=None,
                               project=None, limit: int = 50) -> list[KnowledgeObject]:
        out = self._kos
        if ko_type:
            out = [k for k in out if k.ko_type == ko_type]
        if status:
            out = [k for k in out if k.status == status]
        if person:
            out = [k for k in out if any(person in p for p in k.people)]
        if project:
            out = [k for k in out if k.project and project in k.project]
        return sorted(out, key=lambda k: k.date, reverse=True)[:limit]

    def get_document(self, doc_id: str) -> Document | None:
        return next((d for d in self._documents if d.id == doc_id), None)

    # ── búsqueda ──────────────────────────────────────────────────────
    @staticmethod
    def _terms(query: str) -> list[str]:
        clean = "".join(c if c.isalnum() or c.isspace() else " " for c in query)
        return [t for t in clean.lower().split() if len(t) > 2]

    @classmethod
    def _score(cls, text: str, terms: list[str]) -> int:
        low = text.lower()
        return sum(1 for t in terms if t in low)

    def search_knowledge_objects(self, query: str, limit: int = 20) -> list[KnowledgeObject]:
        terms = self._terms(query)
        if not terms:
            return []
        scored = [(self._score(f"{k.title} {k.statement}", terms), k) for k in self._kos]
        hits = sorted((s for s in scored if s[0]), key=lambda s: -s[0])
        return [k for _, k in hits[:limit]]

    def search_documents(self, query: str, limit: int = 5) -> list[Document]:
        terms = self._terms(query)
        if not terms:
            return []
        scored = [(self._score(f"{d.title} {d.body}", terms), d) for d in self._documents]
        hits = sorted((s for s in scored if s[0]), key=lambda s: -s[0])
        return [d for _, d in hits[:limit]]
