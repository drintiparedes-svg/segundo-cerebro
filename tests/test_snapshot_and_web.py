"""Snapshot de solo lectura y capa web compartida."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro.context import build_context
from segundo_cerebro.ingest import ingest_path
from segundo_cerebro.snapshot import SnapshotStore, export_snapshot, write_snapshot
from segundo_cerebro.store import BrainStore
from segundo_cerebro.ui import render_page
from segundo_cerebro.webapi import dispatch

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "brain" / "inbox" / "2026-08-12-reunion-oncohematologia.md"


@pytest.fixture()
def live_store(tmp_path):
    store = BrainStore(tmp_path / "brain.db")
    ingest_path(store, SAMPLE, prefer_llm=False)
    yield store
    store.close()


def test_export_snapshot_has_full_memory(live_store):
    data = export_snapshot(live_store)
    assert data["version"] == 1
    assert data["kos"] and data["documents"]
    assert any(n["name"] == "Ricardo" for n in data["nodes"])


def test_snapshot_store_matches_live_store(live_store, tmp_path):
    path = tmp_path / "snapshot.json"
    write_snapshot(live_store, path)
    snap = SnapshotStore.from_file(path)

    assert len(snap.list_entities()) == len(live_store.list_entities())
    assert {k.id for k in snap.list_knowledge_objects(limit=999)} == \
           {k.id for k in live_store.list_knowledge_objects(limit=999)}
    assert snap.find_entities("Ricardo")
    assert snap.search_knowledge_objects("oncohematológicos")
    assert snap.search_documents("interoperabilidad")


def test_context_engine_works_over_snapshot(live_store, tmp_path):
    path = tmp_path / "snapshot.json"
    write_snapshot(live_store, path)
    snap = SnapshotStore.from_file(path)

    pack = build_context(snap, "¿Qué debería discutir mañana con Ricardo?")
    assert pack.intent == "strategic"
    assert any(e.name == "Ricardo" for e in pack.entities)
    assert {ko.ko_type for ko in pack.knowledge_objects} >= {"decision", "task"}


def test_dispatch_routes(live_store):
    status, graph = dispatch(live_store, "/api/graph", {})
    assert status == 200 and graph["nodes"]

    status, kos = dispatch(live_store, "/api/kos", {"type": "decision"})
    assert status == 200 and all(k["ko_type"] == "decision" for k in kos)

    status, results = dispatch(live_store, "/api/search", {"q": "oncohematológica"})
    assert status == 200 and "documents" in results

    status, ctx = dispatch(live_store, "/api/context", {"q": "¿Quién trabaja con Ricardo?"})
    assert status == 200 and ctx["intent"] == "relational"

    assert dispatch(live_store, "/api/nope", {})[0] == 404


def test_dispatch_without_memory_is_safe():
    assert dispatch(None, "/api/graph", {})[1] == {"nodes": [], "links": []}
    assert dispatch(None, "/api/kos", {})[1] == []


def test_render_page_is_complete_html():
    page = render_page()
    assert page.startswith("<!doctype html>")
    assert "<title>Segundo Cerebro</title>" in page
    assert page.rstrip().endswith("</html>")
