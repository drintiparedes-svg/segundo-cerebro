"""Pruebas end-to-end del pipeline V1: ingesta → memoria → router → contexto."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro.context import build_context
from segundo_cerebro.ingest import ingest_path, parse_markdown
from segundo_cerebro.router import route
from segundo_cerebro.store import BrainStore

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "brain" / "inbox" / "2026-08-12-reunion-oncohematologia.md"


@pytest.fixture()
def store(tmp_path):
    s = BrainStore(tmp_path / "brain.db")
    yield s
    s.close()


def test_parse_markdown_frontmatter():
    doc = parse_markdown(SAMPLE)
    assert doc.doc_type == "meeting"
    assert doc.date == "2026-08-12"
    assert "Ricardo" in doc.metadata["people"]
    assert doc.title.startswith("Reunión gerencia clínica")


def test_ingest_extracts_knowledge_objects(store):
    summary = ingest_path(store, SAMPLE, prefer_llm=False)
    assert summary["documents"] == 1
    kos = store.list_knowledge_objects()
    types = {ko.ko_type for ko in kos}
    # evento (reunión) + decisión + 2 tareas + 1 pregunta
    assert {"event", "decision", "task", "question"} <= types
    decision = next(ko for ko in kos if ko.ko_type == "decision")
    assert "oncohematológicos" in decision.statement
    assert decision.source_doc is not None
    assert store.get_document(decision.source_doc) is not None


def test_ingest_is_idempotent(store):
    ingest_path(store, SAMPLE, prefer_llm=False)
    before = len(store.list_knowledge_objects())
    summary = ingest_path(store, SAMPLE, prefer_llm=False)
    assert summary["documents"] == 0
    assert summary["skipped"] == 1
    assert len(store.list_knowledge_objects()) == before


def test_graph_links_people_to_project(store):
    ingest_path(store, SAMPLE, prefer_llm=False)
    ricardo = store.find_entities("Ricardo")
    assert ricardo, "Ricardo debe existir como entidad"
    rels = store.relationships_of(ricardo[0].id)
    assert any(r.rel_type == "participates_in" for r in rels)
    assert all(r.valid_from == "2026-08-12" for r in rels)


def test_router_intents():
    assert route("¿Cuándo acordamos el modelo de datos?").intent == "decisional"
    assert route("¿Quién está vinculado con ONCODATA?").intent == "relational"
    assert route("¿Qué tengo pendiente esta semana?").intent == "commitments"
    assert route("¿Qué se habló en la última reunión?").intent == "episodic"
    assert route("¿Qué debería discutir mañana con Ricardo?").intent == "strategic"
    assert route("confianza humano-IA").intent == "semantic"


def test_context_pack_for_strategic_question(store):
    ingest_path(store, SAMPLE, prefer_llm=False)
    pack = build_context(store, "¿Qué debería discutir mañana con Ricardo?")
    assert pack.intent == "strategic"
    assert any(e.name == "Ricardo" for e in pack.entities)
    types = {ko.ko_type for ko in pack.knowledge_objects}
    assert "decision" in types
    assert "task" in types
    md = pack.to_markdown()
    assert "Ricardo" in md and "Knowledge objects" in md


def test_fts_search(store):
    ingest_path(store, SAMPLE, prefer_llm=False)
    kos = store.search_knowledge_objects("oncohematológicos base datos")
    assert kos, "la búsqueda FTS debe encontrar la decisión"
    docs = store.search_documents("interoperabilidad FHIR")
    assert docs
