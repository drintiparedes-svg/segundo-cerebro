"""Memoria estructurada sobre SQLite.

V1 usa SQLite + FTS5 para funcionar sin servicios externos. El esquema es
paralelo al de PostgreSQL/pgvector definido en db/schema.sql, de modo que la
migración a V2/V3 sea un cambio de backend, no de modelo.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import Document, Entity, KnowledgeObject, Relationship

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    date TEXT NOT NULL,
    body TEXT NOT NULL,
    body_hash TEXT NOT NULL UNIQUE,
    metadata TEXT NOT NULL DEFAULT '{}',
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_objects (
    id TEXT PRIMARY KEY,
    ko_type TEXT NOT NULL,
    title TEXT NOT NULL,
    statement TEXT NOT NULL,
    date TEXT NOT NULL,
    people TEXT NOT NULL DEFAULT '[]',
    project TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    confidence TEXT NOT NULL DEFAULT 'probable',
    source_doc TEXT REFERENCES documents(id),
    tags TEXT NOT NULL DEFAULT '[]',
    valid_from TEXT,
    valid_to TEXT
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}',
    UNIQUE(name, entity_type)
);

CREATE TABLE IF NOT EXISTS relationships (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES entities(id),
    target_id TEXT NOT NULL REFERENCES entities(id),
    rel_type TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    confidence TEXT NOT NULL DEFAULT 'probable',
    source_doc TEXT REFERENCES documents(id),
    UNIQUE(source_id, target_id, rel_type, source_doc)
);

-- Learning loop: qué recomendaciones se aceptaron / rechazaron.
CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    verdict TEXT NOT NULL,          -- accepted | rejected | edited
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    id UNINDEXED, title, body
);
CREATE VIRTUAL TABLE IF NOT EXISTS kos_fts USING fts5(
    id UNINDEXED, title, statement
);
"""


class BrainStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: el servidor web (ThreadingHTTPServer) lee
        # desde varios hilos; SQLite serializa internamente los accesos.
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # ── documentos ────────────────────────────────────────────────────────

    def add_document(self, doc: Document) -> bool:
        """Inserta un documento; devuelve False si ya estaba (mismo hash)."""
        body_hash = Document.content_hash(doc.body)
        try:
            self.conn.execute(
                "INSERT INTO documents (id, path, title, doc_type, date, body, "
                "body_hash, metadata, ingested_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (doc.id, doc.path, doc.title, doc.doc_type, doc.date, doc.body,
                 body_hash, json.dumps(doc.metadata, ensure_ascii=False),
                 doc.ingested_at),
            )
        except sqlite3.IntegrityError:
            return False
        self.conn.execute(
            "INSERT INTO documents_fts (id, title, body) VALUES (?,?,?)",
            (doc.id, doc.title, doc.body),
        )
        self.conn.commit()
        return True

    def get_document(self, doc_id: str) -> Document | None:
        row = self.conn.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        return self._row_to_document(row) if row else None

    # ── knowledge objects ─────────────────────────────────────────────────

    def add_knowledge_object(self, ko: KnowledgeObject) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO knowledge_objects (id, ko_type, title, "
            "statement, date, people, project, status, confidence, source_doc, "
            "tags, valid_from, valid_to) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ko.id, ko.ko_type, ko.title, ko.statement, ko.date,
             json.dumps(ko.people, ensure_ascii=False), ko.project, ko.status,
             ko.confidence, ko.source_doc,
             json.dumps(ko.tags, ensure_ascii=False), ko.valid_from, ko.valid_to),
        )
        self.conn.execute(
            "INSERT INTO kos_fts (id, title, statement) VALUES (?,?,?)",
            (ko.id, ko.title, ko.statement),
        )
        self.conn.commit()

    def list_knowledge_objects(
        self,
        ko_type: str | None = None,
        status: str | None = None,
        person: str | None = None,
        project: str | None = None,
        limit: int = 50,
    ) -> list[KnowledgeObject]:
        sql = "SELECT * FROM knowledge_objects WHERE 1=1"
        params: list = []
        if ko_type:
            sql += " AND ko_type = ?"
            params.append(ko_type)
        if status:
            sql += " AND status = ?"
            params.append(status)
        if person:
            sql += " AND people LIKE ?"
            params.append(f"%{person}%")
        if project:
            sql += " AND project LIKE ?"
            params.append(f"%{project}%")
        sql += " ORDER BY date DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_ko(r) for r in rows]

    # ── entidades y relaciones ────────────────────────────────────────────

    def upsert_entity(self, entity: Entity) -> Entity:
        """Inserta la entidad o devuelve la existente (match por nombre+tipo)."""
        row = self.conn.execute(
            "SELECT * FROM entities WHERE name = ? AND entity_type = ?",
            (entity.name, entity.entity_type),
        ).fetchone()
        if row:
            return self._row_to_entity(row)
        self.conn.execute(
            "INSERT INTO entities (id, name, entity_type, aliases, metadata) "
            "VALUES (?,?,?,?,?)",
            (entity.id, entity.name, entity.entity_type,
             json.dumps(entity.aliases, ensure_ascii=False),
             json.dumps(entity.metadata, ensure_ascii=False)),
        )
        self.conn.commit()
        return entity

    def get_entity(self, entity_id: str) -> Entity | None:
        row = self.conn.execute(
            "SELECT * FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        return self._row_to_entity(row) if row else None

    def find_entities(self, name_fragment: str) -> list[Entity]:
        rows = self.conn.execute(
            "SELECT * FROM entities WHERE name LIKE ? OR aliases LIKE ?",
            (f"%{name_fragment}%", f"%{name_fragment}%"),
        ).fetchall()
        return [self._row_to_entity(r) for r in rows]

    def list_entities(self, entity_type: str | None = None) -> list[Entity]:
        if entity_type:
            rows = self.conn.execute(
                "SELECT * FROM entities WHERE entity_type = ? ORDER BY name",
                (entity_type,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM entities ORDER BY entity_type, name"
            ).fetchall()
        return [self._row_to_entity(r) for r in rows]

    def add_relationship(self, rel: Relationship) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO relationships (id, source_id, target_id, "
            "rel_type, valid_from, valid_to, confidence, source_doc) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (rel.id, rel.source_id, rel.target_id, rel.rel_type,
             rel.valid_from, rel.valid_to, rel.confidence, rel.source_doc),
        )
        self.conn.commit()

    def relationships_of(self, entity_id: str) -> list[Relationship]:
        rows = self.conn.execute(
            "SELECT * FROM relationships WHERE source_id = ? OR target_id = ?",
            (entity_id, entity_id),
        ).fetchall()
        return [self._row_to_rel(r) for r in rows]

    # ── búsqueda ──────────────────────────────────────────────────────────

    def search_documents(self, query: str, limit: int = 5) -> list[Document]:
        rows = self.conn.execute(
            "SELECT d.* FROM documents_fts f JOIN documents d ON d.id = f.id "
            "WHERE documents_fts MATCH ? ORDER BY rank LIMIT ?",
            (self._fts_query(query), limit),
        ).fetchall()
        return [self._row_to_document(r) for r in rows]

    def search_knowledge_objects(self, query: str, limit: int = 20) -> list[KnowledgeObject]:
        rows = self.conn.execute(
            "SELECT k.* FROM kos_fts f JOIN knowledge_objects k ON k.id = f.id "
            "WHERE kos_fts MATCH ? ORDER BY rank LIMIT ?",
            (self._fts_query(query), limit),
        ).fetchall()
        return [self._row_to_ko(r) for r in rows]

    @staticmethod
    def _fts_query(query: str) -> str:
        # OR entre términos: recuperación amplia; el ranking FTS5 ordena.
        terms = [t for t in "".join(
            c if c.isalnum() or c.isspace() else " " for c in query
        ).split() if len(t) > 2]
        return " OR ".join(terms) if terms else '""'

    # ── conversores ───────────────────────────────────────────────────────

    @staticmethod
    def _row_to_document(row: sqlite3.Row) -> Document:
        return Document(
            id=row["id"], path=row["path"], title=row["title"],
            doc_type=row["doc_type"], date=row["date"], body=row["body"],
            metadata=json.loads(row["metadata"]), ingested_at=row["ingested_at"],
        )

    @staticmethod
    def _row_to_ko(row: sqlite3.Row) -> KnowledgeObject:
        return KnowledgeObject(
            id=row["id"], ko_type=row["ko_type"], title=row["title"],
            statement=row["statement"], date=row["date"],
            people=json.loads(row["people"]), project=row["project"],
            status=row["status"], confidence=row["confidence"],
            source_doc=row["source_doc"], tags=json.loads(row["tags"]),
            valid_from=row["valid_from"], valid_to=row["valid_to"],
        )

    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> Entity:
        return Entity(
            id=row["id"], name=row["name"], entity_type=row["entity_type"],
            aliases=json.loads(row["aliases"]), metadata=json.loads(row["metadata"]),
        )

    @staticmethod
    def _row_to_rel(row: sqlite3.Row) -> Relationship:
        return Relationship(
            id=row["id"], source_id=row["source_id"], target_id=row["target_id"],
            rel_type=row["rel_type"], valid_from=row["valid_from"],
            valid_to=row["valid_to"], confidence=row["confidence"],
            source_doc=row["source_doc"],
        )
