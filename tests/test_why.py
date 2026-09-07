"""Fase 4: mapa mental de decisiones (sb why), todo local."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro.areas import assign_all, load_areas
from segundo_cerebro.ingest import ingest_path
from segundo_cerebro.models import KnowledgeObject, new_id
from segundo_cerebro.store import BrainStore
from segundo_cerebro.webapi import dispatch
from segundo_cerebro.why import build_dossier, find_decision, to_markdown

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "brain" / "inbox" / "2026-08-12-reunion-oncohematologia.md"


@pytest.fixture()
def store(tmp_path):
    s = BrainStore(tmp_path / "brain.db")
    ingest_path(s, SAMPLE, prefer_llm=False)
    assign_all(s, load_areas(REPO / "brain" / "self" / "areas.md"))
    # una decisión posterior del mismo proyecto, para la cadena
    s.add_knowledge_object(KnowledgeObject(
        id=new_id("ko"), ko_type="decision",
        title="Usar OMOP como modelo común",
        statement="Se adopta OMOP como modelo de datos común.",
        date="2026-09-20", people=["Inti"],
        project="Oncohematology Data Platform", confidence="confirmed",
    ))
    yield s
    s.close()


def test_find_decision_by_text(store):
    ko = find_decision(store, "base oncohematológica")
    assert ko is not None and ko.ko_type == "decision"
    assert "oncohematológicos" in ko.statement


def test_dossier_has_evidence_chain_and_open_items(store):
    dossier = build_dossier(store, "base oncohematológica validada")
    assert dossier is not None
    assert dossier["source"]["doc_type"] == "meeting"
    # la decisión OMOP posterior aparece en la cadena
    assert any("OMOP" in k["statement"] for k in dossier["after"])
    assert dossier["questions"], "la pregunta FHIR vs OMOP quedó abierta al decidir"
    assert len(dossier["tasks"]) == 2

    md = to_markdown(dossier, {"falp": "FALP · Informática Médica"})
    assert "Por qué:" in md and "Cadena de decisiones" in md
    assert "FALP · Informática Médica" in md
    assert "Reconstruido localmente" in md


def test_dossier_none_when_no_match(store):
    assert build_dossier(store, "zzz inexistente qqq") is None


def test_why_api(store):
    status, payload = dispatch(store, "/api/why", {"q": "oncohematológica"})
    assert status == 200 and payload["found"]
    assert "Cadena" in payload["markdown"] or "Por qué" in payload["markdown"]


def test_graph_includes_decision_nodes(store):
    status, graph = dispatch(store, "/api/graph", {})
    dec_nodes = [n for n in graph["nodes"] if n["type"] == "decision"]
    assert len(dec_nodes) >= 2
    ids = {n["id"] for n in dec_nodes}
    # cadena cronológica dentro del proyecto
    assert any(l["type"] == "precedes" and l["source"] in ids and l["target"] in ids
               for l in graph["links"])
    # conectadas al proyecto
    assert any(l["type"] == "shapes" for l in graph["links"])
