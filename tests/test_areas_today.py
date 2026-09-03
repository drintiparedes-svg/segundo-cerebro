"""Fase 1: áreas de trabajo y brief del día — todo local, sin red."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro.areas import Area, assign_all, classify, load_areas
from segundo_cerebro.ingest import ingest_path
from segundo_cerebro.store import BrainStore
from segundo_cerebro.today import build_today
from segundo_cerebro.webapi import dispatch

REPO = Path(__file__).resolve().parents[1]
AREAS_FILE = REPO / "brain" / "self" / "areas.md"
SAMPLE = REPO / "brain" / "inbox" / "2026-08-12-reunion-oncohematologia.md"


@pytest.fixture()
def store(tmp_path):
    s = BrainStore(tmp_path / "brain.db")
    ingest_path(s, SAMPLE, prefer_llm=False)
    yield s
    s.close()


def test_load_seed_areas():
    areas = load_areas(AREAS_FILE)
    ids = {a.id for a in areas}
    assert {"falp", "clinica", "medismart", "academia", "personal"} <= ids


def test_classify_prefers_projects_and_people():
    areas = [
        Area(id="a", name="A", keywords=["datos"]),
        Area(id="b", name="B", people=["Ricardo"], projects=["ONCODATA"]),
    ]
    assert classify("avance de datos ONCODATA", [], "ONCODATA", areas) == "b"
    assert classify("reunión con equipo", ["Ricardo"], None, areas) == "b"
    # sin señal suficiente → None, nunca adivinar
    assert classify("almuerzo", [], None, areas) is None


def test_assign_all_labels_memory(store):
    areas = load_areas(AREAS_FILE)
    summary = assign_all(store, areas)
    assert summary["documents"] >= 1
    docs = [d for d in store.list_documents() if "oncohematologia" in d.path]
    assert docs[0].area == "falp"
    # los KOs heredan el área del documento fuente
    decision = store.list_knowledge_objects(ko_type="decision")[0]
    assert decision.area == "falp"
    assert store.list_knowledge_objects(area="falp")


def test_assign_is_recalculable(store):
    areas = load_areas(AREAS_FILE)
    assign_all(store, areas)
    first = store.area_counts()
    assign_all(store, areas)
    assert store.area_counts() == first


def test_areas_api(store):
    areas_file_cwd = Path.cwd() / "brain" / "self" / "areas.md"
    if not areas_file_cwd.exists():
        pytest.skip("requiere el mapa de áreas del repo")
    assign_all(store, load_areas(areas_file_cwd))
    status, payload = dispatch(store, "/api/areas", {})
    assert status == 200
    falp = next(a for a in payload if a["id"] == "falp")
    assert falp["decisions"] >= 1 and falp["tasks_open"] >= 1


def test_today_brief_groups_by_area(store, tmp_path):
    areas = load_areas(AREAS_FILE)
    assign_all(store, areas)
    brief = build_today(store, tmp_path, areas)
    assert "Compromisos abiertos" in brief
    assert "FALP · Informática Médica" in brief
    assert "ninguna llamada externa" in brief
