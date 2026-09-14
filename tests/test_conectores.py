"""Fase A — Connector SDK: registro, procedencia por documento y desconexión
con purga. Todo local, sin red."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro.connectors import registry
from segundo_cerebro.connectors.base import (Connector, ConnectorSpec, SyncResult,
                                             connector_id_for, load_registry_file)
from segundo_cerebro.connectors.localfs import add_source, load_registry, sync_source
from segundo_cerebro.ingest import ingest_path
from segundo_cerebro.models import Document, new_id
from segundo_cerebro.refresh import run_refresh
from segundo_cerebro.store import BrainStore
from segundo_cerebro.webapi import dispatch, dispatch_post

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "brain" / "inbox" / "2026-08-12-reunion-oncohematologia.md"


@pytest.fixture()
def store(tmp_path):
    s = BrainStore(tmp_path / "b.db")
    yield s
    s.close()


def _folder(root: Path, name: str, n: int = 2) -> Path:
    d = root / name
    d.mkdir()
    for i in range(n):
        (d / f"nota{i}.md").write_text(f"# {name} {i}\n\nDECISIÓN: decisión {name} {i}.\n\n- [ ] tarea {name} {i}\n",
                                       encoding="utf-8")
    return d


def test_types_and_plugin_registration():
    ids = {t["id"] for t in registry.types_payload()}
    assert {"localfs", "gdrive", "gcalendar", "gmail", "zotero", "chats"} <= ids
    for t in registry.types_payload():
        assert t["kind"] in ("local", "cloud", "api") and t["privacy"] in ("local", "read-cloud", "write-cloud")

    class FakeConnector(Connector):
        spec = ConnectorSpec(id="fake", name="Fake", kind="api", privacy="read-cloud",
                             config_schema={"token": {"required": True}})

        def sync(self, store):
            return SyncResult()

    registry.register_type(FakeConnector)
    assert "fake" in registry.connector_types()
    registry.BUILTIN.pop("fake")


def test_add_test_sync_and_disconnect_with_purge(store, tmp_path):
    ingest_path(store, SAMPLE, prefer_llm=False)        # entidades del vault (Ricardo, FALP…)
    entities_before = len(store.list_entities())
    assert entities_before > 0
    a = _folder(tmp_path, "Tesis", 2)
    b = _folder(tmp_path, "FALP", 3)
    ia = registry.add_instance(tmp_path, "localfs", {"path": str(a)})
    ib = registry.add_instance(tmp_path, "localfs", {"path": str(b), "alias": "Gestión"})
    assert ia["id"] == "localfs:Tesis" and ib["id"] == "localfs:Gesti-n"
    assert registry.add_instance(tmp_path, "localfs", {"path": str(a), "alias": "Tesis"})["id"] == ia["id"], "idempotente"
    with pytest.raises(ValueError):
        registry.add_instance(tmp_path, "zotero", {})
    with pytest.raises(KeyError):
        registry.add_instance(tmp_path, "nope", {})
    assert registry.test_instance(tmp_path, ia["id"])["ok"]
    assert not registry.test_instance(tmp_path, "localfs:zzz")["ok"]

    summary = registry.sync_instances(store, tmp_path)
    assert summary["documents"] == 5 and summary["knowledge_objects"] >= 10
    assert summary["instances"][ia["id"]]["added"] == 2
    counts = store.count_by_connector()
    assert counts == {ia["id"]: 2, ib["id"]: 3}
    assert all(d.connector_id in counts for d in store.list_documents() if d.connector_id)
    inst = registry.get_instance(tmp_path, ia["id"])
    assert inst["last_sync"] and inst["last_result"]["added"] == 2 and inst["state"]["last_mtime"]
    again = registry.sync_instances(store, tmp_path)
    assert again["documents"] == 0, "incremental: nada se duplica"
    assert registry.get_instance(tmp_path, ia["id"])["last_result"]["unchanged"] == 2

    kos_before = len(store.list_knowledge_objects(limit=1000))
    r = registry.remove_instance(tmp_path, store, ia["id"], purge=True)
    assert r["documents"] == 2 and r["kos"] >= 4
    assert store.count_by_connector() == {ib["id"]: 3}, "solo borra lo suyo"
    assert len(store.list_knowledge_objects(limit=1000)) == kos_before - r["kos"]
    assert registry.get_instance(tmp_path, ia["id"]) is None
    assert len(store.list_entities()) == entities_before, "las entidades se conservan"
    assert store.get_document(store.list_documents()[0].id), "el vault sigue intacto"

    r = registry.remove_instance(tmp_path, store, ib["id"], purge=False)
    assert r["documents"] == 0 and store.count_by_connector() == {ib["id"]: 3}, "sin purga conserva"


def test_google_instances_discovered_and_disabled_not_deleted(store, tmp_path):
    gdir = tmp_path / "google"
    gdir.mkdir()
    (gdir / "token-falp.json").write_text("{}")
    data = registry.load_instances(tmp_path)
    ids = {i["id"] for i in data["instances"]}
    assert {"gdrive:falp", "gcalendar:falp", "gmail:falp"} <= ids
    r = registry.remove_instance(tmp_path, store, "gdrive:falp", purge=True)
    assert r["documents"] == 0
    inst = registry.get_instance(tmp_path, "gdrive:falp")
    assert inst is not None and inst["enabled"] is False, "Google queda deshabilitada, no se redescubre"
    assert registry.get_instance(tmp_path, "gmail:falp")["enabled"] is True
    registry.remove_instance(tmp_path, store, "gcalendar:falp")
    registry.remove_instance(tmp_path, store, "gmail:falp", forget=True)
    assert not (gdir / "token-falp.json").exists(), "última instancia con --forget borra el token"


def test_legacy_sources_json_migrates_and_compat_registry(store, tmp_path):
    d = _folder(tmp_path, "Escritorio", 1)
    (tmp_path / "sources.json").write_text(json.dumps({
        "sources": [{"path": str(d), "alias": "Escritorio", "added_at": "2026-01-01T00:00:00Z"}],
        "state": {str(d): {"last_mtime": 1.0, "last_sync": "2026-01-02T00:00:00Z"}},
        "ignored": ["/x/Fotos"]}), encoding="utf-8")
    reg = load_registry(tmp_path)
    assert reg["sources"][0]["alias"] == "Escritorio" and reg["ignored"] == ["/x/Fotos"]
    assert reg["state"][str(d)]["last_mtime"] == 1.0
    assert not (tmp_path / "sources.json").exists() and (tmp_path / "sources.json.migrated").exists()
    assert registry.get_instance(tmp_path, "localfs:Escritorio")["last_sync"] == "2026-01-02T00:00:00Z"

    # la vía antigua sigue funcionando y escribe en connectors.json
    e = _folder(tmp_path, "Otra", 1)
    add_source(tmp_path, e)
    assert registry.get_instance(tmp_path, "localfs:Otra")
    r = sync_source(store, tmp_path, {"path": str(e), "alias": "Otra"})
    assert r["added"] == 1 and registry.get_instance(tmp_path, "localfs:Otra")["state"]["last_sync"]
    assert store.list_documents()[0].connector_id == "localfs:Otra", "procedencia deducida"


def test_connector_id_for_legacy_documents_and_backfill(tmp_path):
    db = tmp_path / "b.db"
    s = BrainStore(db)
    ingest_path(s, SAMPLE, prefer_llm=False)
    assert connector_id_for(Document(id="x", path="p", title="t", doc_type="note", date="2026-01-01",
                                     body="b", metadata={"source": "google-drive", "account": "falp"})) == "gdrive:falp"
    assert connector_id_for(Document(id="x", path="p", title="t", doc_type="note", date="2026-01-01",
                                     body="b", metadata={"source": "local-folder", "source_alias": "subida-manual"})) == "upload"
    # simula una base anterior al SDK: columna vacía → se rellena al abrir
    s.conn.execute("UPDATE documents SET connector_id = NULL")
    s.conn.execute("UPDATE documents SET metadata = ?", (json.dumps({"source": "zotero"}),))
    s.conn.commit()
    s.close()
    s2 = BrainStore(db)
    assert s2.list_documents()[0].connector_id == "zotero:manual"
    s2.close()


def test_refresh_uses_registry_and_api_roundtrip(store, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    d = _folder(tmp_path, "Proyectos", 2)
    st, res = dispatch_post(store, "/api/connectors/add", {},
                            json.dumps({"type": "localfs", "config": {"path": str(d)}}).encode())
    assert st == 200 and res["instance"]["id"] == "localfs:Proyectos"
    assert any(i["id"] == "localfs:Proyectos" for i in res["instances"])
    st, res = dispatch_post(store, "/api/connectors/test", {}, json.dumps({"id": "localfs:Proyectos"}).encode())
    assert st == 200 and res["ok"]

    state = run_refresh(store, tmp_path)
    assert state["steps"]["connectors"]["documents"] == 2
    assert state["steps"]["mail"]["skipped"].startswith("sin cuentas Gmail")

    st, res = dispatch(store, "/api/connectors", {})
    inst = next(i for i in res["instances"] if i["id"] == "localfs:Proyectos")
    assert inst["documents"] == 2 and inst["privacy"] == "local" and inst["last_sync"]
    assert any(t["id"] == "gdrive" for t in res["types"])

    st, res = dispatch_post(store, "/api/connectors/remove", {},
                            json.dumps({"id": "localfs:Proyectos", "purge": True}).encode())
    assert st == 200 and res["documents"] == 2 and res["instances"] == []
    assert store.count_by_connector() == {}
    st, res = dispatch_post(store, "/api/connectors/remove", {}, json.dumps({"id": "nope"}).encode())
    assert st == 400
