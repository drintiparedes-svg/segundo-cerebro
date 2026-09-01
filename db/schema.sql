-- Esquema objetivo para V2+: PostgreSQL + pgvector.
-- V1 corre sobre SQLite (src/segundo_cerebro/store.py) con un esquema paralelo;
-- migrar es cambiar de backend, no de modelo de datos.

CREATE EXTENSION IF NOT EXISTS vector;

-- ── documento fuente (capa de captura) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    path        TEXT NOT NULL,
    title       TEXT NOT NULL,
    doc_type    TEXT NOT NULL,              -- meeting | note | paper | email | transcript
    date        DATE NOT NULL,              -- fecha del contenido
    body        TEXT NOT NULL,
    body_hash   TEXT NOT NULL UNIQUE,
    metadata    JSONB NOT NULL DEFAULT '{}',
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── memoria semántica: chunks con embeddings ───────────────────────────
CREATE TABLE IF NOT EXISTS chunks (
    id        TEXT PRIMARY KEY,
    doc_id    TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal   INT  NOT NULL,
    content   TEXT NOT NULL,
    embedding vector(1024)                  -- dimensión según modelo de embeddings
);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

-- ── knowledge objects: la unidad fundamental ───────────────────────────
CREATE TABLE IF NOT EXISTS knowledge_objects (
    id         TEXT PRIMARY KEY,
    ko_type    TEXT NOT NULL CHECK (ko_type IN
                ('decision','task','fact','idea','question','hypothesis','event')),
    title      TEXT NOT NULL,
    statement  TEXT NOT NULL,
    date       DATE NOT NULL,
    people     JSONB NOT NULL DEFAULT '[]',
    project    TEXT,
    status     TEXT NOT NULL DEFAULT 'active'
               CHECK (status IN ('active','done','superseded','archived')),
    confidence TEXT NOT NULL DEFAULT 'probable'
               CHECK (confidence IN ('confirmed','probable','tentative')),
    source_doc TEXT REFERENCES documents(id),
    tags       JSONB NOT NULL DEFAULT '[]',
    valid_from DATE,
    valid_to   DATE                          -- NULL = sigue vigente
);
CREATE INDEX IF NOT EXISTS kos_type_date_idx ON knowledge_objects (ko_type, date DESC);

-- ── knowledge graph ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS entities (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN
                 ('person','organization','project','concept')),
    aliases     JSONB NOT NULL DEFAULT '[]',
    metadata    JSONB NOT NULL DEFAULT '{}',
    UNIQUE (name, entity_type)
);

CREATE TABLE IF NOT EXISTS relationships (
    id         TEXT PRIMARY KEY,
    source_id  TEXT NOT NULL REFERENCES entities(id),
    target_id  TEXT NOT NULL REFERENCES entities(id),
    rel_type   TEXT NOT NULL,
    valid_from DATE,
    valid_to   DATE,                         -- temporalidad de la relación
    confidence TEXT NOT NULL DEFAULT 'probable',
    source_doc TEXT REFERENCES documents(id),
    UNIQUE (source_id, target_id, rel_type, source_doc)
);

-- ── learning loop ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS feedback (
    id         TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,               -- KO o recomendación evaluada
    verdict    TEXT NOT NULL CHECK (verdict IN ('accepted','rejected','edited')),
    note       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
