"""Fase C — autonomía supervisada: matriz con techo, bandeja con
ejecución/aprobación/deshacer, escritura opt-in y agentes de flujo."""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro import ai, autonomy, queue
from segundo_cerebro.agents.flows import build_meeting_prep, run_flows
from segundo_cerebro.agents import save_latest_triage
from segundo_cerebro.connectors.google_auth import WRITE_SCOPES, has_write_scope
from segundo_cerebro.models import KnowledgeObject, new_id
from segundo_cerebro.people import set_person_override
from segundo_cerebro.refresh import run_refresh
from segundo_cerebro.store import BrainStore
from segundo_cerebro.webapi import dispatch, dispatch_post

MONDAY = date(2026, 9, 14)


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SB_DB_PATH", str(tmp_path / "b.db"))
    monkeypatch.delenv("SB_AI_OFF", raising=False)
    s = BrainStore(tmp_path / "b.db")
    yield s
    s.close()


@pytest.fixture()
def fake_executors(monkeypatch):
    """Ejecutores dobles: registran llamadas, sin tocar Google."""
    calls = {"calendar": [], "calendar_deleted": [], "gmail": [], "gmail_deleted": []}

    def cal(payload, brain_dir, store):
        calls["calendar"].append(payload)
        return {"event_id": "ev1", "undo": {"account": payload["account"], "event_id": "ev1"}}

    def cal_undo(result, brain_dir, store):
        calls["calendar_deleted"].append(result["undo"]["event_id"])

    def gm(payload, brain_dir, store):
        calls["gmail"].append(payload)
        return {"draft_id": "dr1", "undo": {"account": payload["account"], "draft_id": "dr1"}}

    def gm_undo(result, brain_dir, store):
        calls["gmail_deleted"].append(result["undo"]["draft_id"])

    monkeypatch.setitem(queue.EXECUTORS, "calendar_block", (cal, cal_undo))
    monkeypatch.setitem(queue.EXECUTORS, "gmail_draft", (gm, gm_undo))
    return calls


def _ko(store, ko_type, title, **kw):
    ko = KnowledgeObject(id=new_id("ko"), ko_type=ko_type, title=title, statement=kw.pop("statement", title),
                         date=kw.pop("date", "2026-09-01"), **kw)
    store.add_knowledge_object(ko)
    return ko


def test_matrix_defaults_ceilings_and_ai_off(tmp_path, monkeypatch):
    monkeypatch.setenv("SB_DB_PATH", str(tmp_path / "b.db"))
    levels = autonomy.load_levels(tmp_path)
    assert levels["focus_block"] == "L3+" and levels["send_email"] == "L2" and levels["suggest_people"] == "L1"
    with pytest.raises(ValueError):
        autonomy.set_level(tmp_path, "send_email", "L3")        # irreversible: techo L2
    with pytest.raises(ValueError):
        autonomy.set_level(tmp_path, "meeting_prep", "L3+")     # sobre el techo
    with pytest.raises(KeyError):
        autonomy.set_level(tmp_path, "nope", "L1")
    assert autonomy.set_level(tmp_path, "meeting_prep", "L3") == "L3"
    assert autonomy.decide(tmp_path, "meeting_prep") == "auto"
    assert autonomy.set_level(tmp_path, "focus_block", "L2") == "L2"
    assert autonomy.decide(tmp_path, "focus_block") == "queue"
    assert autonomy.decide(tmp_path, "suggest_people") == "suggest"
    rows = {r["id"]: r for r in autonomy.matrix(tmp_path)}
    assert rows["send_email"]["class"] == "L4" and rows["send_email"]["options"] == ["L0", "L1", "L2"]
    assert rows["meeting_prep"]["level"] == "L3"

    ai.switch_off(tmp_path, reason="prueba", remove_schedule=False)
    assert autonomy.effective_level(tmp_path, "meeting_prep") == "L2"
    assert autonomy.decide(tmp_path, "classify_areas") == "queue", "con IA apagada nada corre solo"
    assert {r["id"]: r["effective"] for r in autonomy.matrix(tmp_path)}["daily_brief"] == "L2"
    ai.switch_on(tmp_path)
    assert autonomy.decide(tmp_path, "classify_areas") == "auto"


def test_queue_lifecycle_execute_approve_reject_undo(store, tmp_path, fake_executors):
    # L3+ → se ejecuta y se puede deshacer
    item = queue.submit(tmp_path, store, "focus_block", "calendar_block", "Bloque",
                        {"account": "falp", "summary": "Foco", "start": "2026-09-14T09:00:00", "end": "2026-09-14T11:00:00"},
                        key="focus_block:x")
    assert item["status"] == "executed" and item["result"]["event_id"] == "ev1"
    assert fake_executors["calendar"] and queue.exists(tmp_path, "focus_block:x")
    assert queue.submit(tmp_path, store, "focus_block", "calendar_block", "Bloque", {}, key="focus_block:x")["duplicate"]
    undone = queue.undo(tmp_path, store, item["id"])
    assert undone["status"] == "undone" and fake_executors["calendar_deleted"] == ["ev1"]
    assert not queue.exists(tmp_path, "focus_block:x"), "deshecho → se puede volver a proponer"

    # L2 → espera; aprobar ejecuta; rechazar no
    item = queue.submit(tmp_path, store, "meeting_prep", "draft_note", "Prep",
                        {"kind": "prep", "markdown": "# Prep\n\nhola"}, key="meeting_prep:e1")
    assert item["status"] == "pending"
    st, res = dispatch(store, "/api/queue", {})
    assert res["summary"]["pending"] == 1 and res["items"][0]["id"] == item["id"]
    approved = queue.approve(tmp_path, store, item["id"])
    assert approved["status"] == "executed" and Path(approved["result"]["path"]).exists()
    assert (tmp_path / "drafts").is_dir()
    queue.undo(tmp_path, store, item["id"])
    assert not Path(approved["result"]["path"]).exists()

    other = queue.submit(tmp_path, store, "send_email", "gmail_send", "Enviar", {"to": "x"}, key="send:1")
    assert other["status"] == "pending", "irreversible: nunca automático"
    rejected = queue.reject(tmp_path, other["id"], reason="no corresponde")
    assert rejected["status"] == "rejected"
    manual = queue.submit(tmp_path, store, "send_email", "gmail_send", "Enviar 2", {"to": "x"}, key="send:2")
    assert queue.approve(tmp_path, store, manual["id"])["status"] == "manual", "sin ejecutor → lo haces tú"

    # sugerencia (L1): queda visible, no se ejecuta
    sug = queue.submit(tmp_path, store, "suggest_people", "draft_note", "Fija a Ana", {}, key="sp:1")
    assert sug["status"] == "suggested"
    log = (tmp_path / "logs" / "actions.log").read_text(encoding="utf-8")
    assert "EJECUTADO" in log and "DESHECHO" in log and "RECHAZADO" in log and "APROBADO" in log


def test_write_scope_detection(tmp_path):
    gdir = tmp_path / "google"
    gdir.mkdir()
    (gdir / "token-falp.json").write_text(json.dumps({"scopes": ["https://www.googleapis.com/auth/drive.readonly"]}))
    assert has_write_scope("falp", gdir) is False
    (gdir / "token-falp.json").write_text(json.dumps({"scopes": WRITE_SCOPES + ["x"]}))
    assert has_write_scope("falp", gdir) is True
    assert has_write_scope("nadie", gdir) is False


def test_flows_prepare_meetings_focus_blocks_replies_and_weekly(store, tmp_path, fake_executors):
    tomorrow = str(MONDAY + timedelta(days=1))
    meeting = _ko(store, "event", "Reunión comité de datos", date=tomorrow, people=["Ricardo"])
    _ko(store, "task", "Enviar variables mínimas", people=["Ricardo"], valid_to=str(MONDAY + timedelta(days=1)), effort_h=2.0)
    _ko(store, "question", "¿Estándar?", people=["Ricardo"])
    _ko(store, "task", "Cosa chica", valid_to=str(MONDAY), effort_h=0.5)     # < 1 h → sin bloque
    md = build_meeting_prep(store, meeting)
    assert "## Ricardo" in md and "Enviar variables mínimas" in md and "Agenda propuesta" in md

    # sin cuenta de calendario ni gmail: los externos caen a la bandeja
    set_person_override(tmp_path, "Ricardo", pin=True)
    save_latest_triage(tmp_path, [{"id": "m1", "account": "falp", "priority": 1,
                                   "from": "Ricardo Morales <r@falp.org>", "subject": "Urgente", "reasons": []}])
    r = run_flows(store, tmp_path, today=MONDAY)
    titles = {i["title"] for i in r["queued"]}
    assert any(t.startswith("Preparar «Reunión comité") for t in titles)
    assert any(t.startswith("Bloque de foco: Enviar variables") for t in titles)
    assert any(t.startswith("Borrador de respuesta a Ricardo") for t in titles)
    assert any(i["title"].startswith("Revisión semanal") for i in r["executed"]), "lunes: L3 automático"
    assert not fake_executors["calendar"] and not fake_executors["gmail"]
    again = run_flows(store, tmp_path, today=MONDAY)
    assert again["created"] == [] and again["duplicates"] >= 4, "idempotente"

    # con cuentas Google habilitadas, L3+ ejecuta solo (aquí con ejecutores dobles)
    gdir = tmp_path / "google"; gdir.mkdir()
    (gdir / "token-falp.json").write_text("{}")
    for it in queue.list_items(tmp_path, status="pending"):
        queue.reject(tmp_path, it["id"])
    r = run_flows(store, tmp_path, today=MONDAY)
    assert any(i["title"].startswith("Bloque de foco") for i in r["executed"])
    assert fake_executors["calendar"][0]["account"] == "falp" and fake_executors["calendar"][0]["summary"].startswith("Foco ·")
    assert fake_executors["gmail"][0]["to"].startswith("Ricardo") and "[Borrador" in fake_executors["gmail"][0]["body"]

    # con IA apagada: nada se ejecuta solo
    for it in queue.list_items(tmp_path):
        if it["status"] == "executed":
            queue.undo(tmp_path, store, it["id"])
        elif it["status"] == "pending":
            queue.reject(tmp_path, it["id"])
    ai.switch_off(tmp_path, reason="t", remove_schedule=False)
    n_cal = len(fake_executors["calendar"])
    r = run_flows(store, tmp_path, today=MONDAY)
    assert r["executed"] == [] and len(fake_executors["calendar"]) == n_cal and r["queued"]
    ai.switch_on(tmp_path)


def test_refresh_runs_flows_and_api(store, tmp_path, monkeypatch, fake_executors):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    state = run_refresh(store, tmp_path)
    assert state["steps"]["flows"]["ok"] and "created" in state["steps"]["flows"]
    st, res = dispatch(store, "/api/autonomy", {})
    assert st == 200 and any(r["id"] == "focus_block" for r in res["matrix"])
    st, res = dispatch_post(store, "/api/autonomy/set", {}, json.dumps({"action": "send_email", "level": "L3"}).encode())
    assert st == 403
    st, res = dispatch_post(store, "/api/autonomy/set", {}, json.dumps({"action": "meeting_prep", "level": "L3"}).encode())
    assert st == 200 and {r["id"]: r["level"] for r in res["matrix"]}["meeting_prep"] == "L3"
    _ko(store, "event", "Reunión mañana", date=str(date.today() + timedelta(days=1)), people=["Ana"])
    st, res = dispatch_post(store, "/api/queue/run", {}, b"{}")
    assert st == 200 and res["run"]["executed"], "meeting_prep en L3 se ejecuta al correr los flujos"
    item = res["items"][0]
    st, res = dispatch_post(store, "/api/queue/undo", {}, json.dumps({"id": item["id"]}).encode())
    assert st == 200 and res["item"]["status"] == "undone"
    assert dispatch_post(store, "/api/queue/approve", {}, json.dumps({"id": "nope"}).encode())[0] == 404
