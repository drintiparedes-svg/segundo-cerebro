"""Fase B — cockpit de carga: capacidad, esfuerzo inferido/ajustable,
planificación greedy de 7 días, cierre de tareas. Todo local."""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro.config import load_config
from segundo_cerebro.connectors.gcalendar import event_to_document
from segundo_cerebro.models import Document, KnowledgeObject, new_id
from segundo_cerebro.store import BrainStore
from segundo_cerebro.webapi import dispatch, dispatch_post
from segundo_cerebro.workload import (capacity_hours, estimate_effort, meetings_by_day,
                                      parse_duration_hours, plan_week, projection_lines,
                                      today_lines)

MONDAY = date(2026, 9, 14)   # lunes


@pytest.fixture()
def store(tmp_path):
    s = BrainStore(tmp_path / "b.db")
    yield s
    s.close()


def _task(store, title, due=None, effort=None, tags=(), project=None, area="academia", status="active"):
    ko = KnowledgeObject(id=new_id("ko"), ko_type="task", title=title, statement=title,
                         date="2026-09-01", project=project, status=status, tags=list(tags),
                         valid_to=due, area=area, effort_h=effort)
    store.add_knowledge_object(ko)
    return ko


def _meeting(store, day, minutes):
    ev = {"id": f"ev-{day}-{minutes}", "summary": "Reunión", "status": "confirmed",
          "start": {"dateTime": f"{day}T10:00:00-03:00"},
          "end": {"dateTime": f"{day}T10:{minutes:02d}:00-03:00" if minutes < 60 else f"{day}T{10 + minutes // 60}:{minutes % 60:02d}:00-03:00"},
          "attendees": [{"displayName": "Ricardo"}]}
    doc = event_to_document(ev, "falp")
    assert doc.metadata["duration_min"] == minutes and doc.metadata["all_day"] is False
    store.add_document(doc)
    return doc


def test_capacity_and_duration_parsing(tmp_path):
    cfg = load_config(tmp_path)
    assert capacity_hours(cfg, MONDAY) == 9.5
    assert capacity_hours(cfg, MONDAY + timedelta(days=5)) == 0.0, "sábado sin jornada"
    assert parse_duration_hours("5 días") == 20.0 and parse_duration_hours("3 h") == 3.0
    assert parse_duration_hours("90 min") == 1.5 and parse_duration_hours("2 semanas") == 40.0
    assert parse_duration_hours("por definir") is None and parse_duration_hours(None) is None


def test_effort_sources_in_order(store):
    fixed = _task(store, "ajustada", effort=2.5, tags=["duracion:5 días"])
    plan = _task(store, "del plan", tags=["duracion:2 días"], project="MSc Thesis")
    assert estimate_effort(fixed) == (2.5, "ajustado")
    assert estimate_effort(plan) == (8.0, "plan")
    _task(store, "cerrada 1", effort=3.0, project="ONCODATA", status="done")
    _task(store, "cerrada 2", effort=5.0, project="ONCODATA", status="done")
    from segundo_cerebro.workload import history_medians
    hist = _task(store, "nueva del proyecto", project="ONCODATA")
    assert estimate_effort(hist, history_medians(store)) == (4.0, "histórico")
    assert estimate_effort(_task(store, "sin pistas")) == (1.0, "tipo")


def test_plan_week_overdue_first_fits_and_flags_overload(store, tmp_path):
    cfg = load_config(tmp_path)
    _meeting(store, str(MONDAY), 120)                      # lunes: 2 h de agenda
    _meeting(store, str(MONDAY + timedelta(days=1)), 30)
    late = _task(store, "atrasada", due=str(MONDAY - timedelta(days=3)), effort=2.0)
    soon = _task(store, "vence miércoles", due=str(MONDAY + timedelta(days=2)), effort=3.0)
    big = _task(store, "enorme", due=str(MONDAY + timedelta(days=1)), effort=30.0)
    free = _task(store, "sin fecha", effort=1.0, area="personal")

    plan = plan_week(store, cfg, today=MONDAY, area_rank={"academia": 1, "personal": 5})
    assert plan["days"][0]["meetings_h"] == 2.0 and plan["days"][1]["meetings_h"] == 0.5
    assert round(plan["days"][0]["focus_h"], 2) == round((9.5 - 2.0) * 0.6, 2)
    mon = plan["days"][0]
    assert [i["title"] for i in mon["items"]][0] == "atrasada", "atrasadas primero"
    assert any(i["title"] == "vence miércoles" for i in plan["days"][2]["items"]), \
        "no cabe el lunes (2.5 h libres) ni el martes (ocupado por la enorme) → miércoles, su límite"
    tue = plan["days"][1]
    assert any(i["title"] == "enorme" for i in tue["items"]) and tue["overloaded"], \
        "no cabe → su día límite, marcado sobrecargado"
    assert "2026-09-15" in plan["totals"]["overloaded_days"]
    assert plan["days"][5]["capacity_h"] == 0 and plan["days"][5]["items"] == []
    assert plan["unscheduled"] == []
    assert store.get_knowledge_object(late.id).scheduled_for == str(MONDAY), "se persiste el día"

    lines = today_lines(plan)
    assert lines[0].startswith("## Carga de hoy — 2.0 h de agenda")
    assert any("⚠ atrasada" in l for l in lines)
    proj = projection_lines(plan)
    assert proj[0] == "## Proyección de la semana" and any("⚠" in l for l in proj)
    assert any("sobrecargados" in l for l in proj)

    # cerrar la atrasada y fijar otra a un día: el planificador respeta ambas
    store.update_ko(late.id, status="done")
    store.update_ko(free.id, scheduled_for=str(MONDAY + timedelta(days=3)), tags=["fijado"])
    plan2 = plan_week(store, cfg, today=MONDAY)
    assert all(i["title"] != "atrasada" for d in plan2["days"] for i in d["items"])
    thu = plan2["days"][3]
    assert any(i["title"] == "sin fecha" and i["fixed"] for i in thu["items"])


def test_no_capacity_window_leaves_tasks_unscheduled(store, tmp_path):
    cfg = load_config(tmp_path)
    cfg["workday"]["days"] = []          # semana sin jornada (vacaciones)
    _task(store, "algo", effort=1.0)
    plan = plan_week(store, cfg, today=MONDAY)
    assert plan["totals"]["unscheduled"] == 1 and plan["unscheduled"][0]["title"] == "algo"


def test_meetings_default_and_all_day(store, tmp_path):
    cfg = load_config(tmp_path)
    allday = event_to_document({"id": "a", "summary": "Congreso", "start": {"date": str(MONDAY)},
                                "end": {"date": str(MONDAY + timedelta(days=1))}}, "falp")
    assert allday.metadata["all_day"] is True and allday.metadata["duration_min"] is None
    store.add_document(allday)
    nodur = event_to_document({"id": "b", "summary": "Llamada", "start": {"dateTime": f"{MONDAY}T15:00:00-03:00"}}, "falp")
    store.add_document(nodur)
    hours = meetings_by_day(store, MONDAY, 7, cfg)
    assert hours[str(MONDAY)] == 1.0, "sin fin → 60 min por defecto; día completo no resta"


def test_update_ko_and_api(store, tmp_path):
    t = _task(store, "revisar SDK", due=str(MONDAY + timedelta(days=1)), effort=None)
    with pytest.raises(ValueError):
        store.update_ko(t.id, ko_type="event")
    st, res = dispatch_post(store, "/api/kos/update", {},
                            json.dumps({"id": t.id, "effort_h": 2.5, "scheduled_for": str(MONDAY), "fixed": True}).encode())
    assert st == 200 and res["ko"]["effort_h"] == 2.5 and "fijado" in res["ko"]["tags"]
    assert "days" in res["workload"]
    st, res = dispatch_post(store, "/api/kos/update", {}, json.dumps({"id": t.id, "status": "done"}).encode())
    assert st == 200 and res["ko"]["status"] == "done"
    assert dispatch_post(store, "/api/kos/update", {}, json.dumps({"id": "nope"}).encode())[0] == 404
    assert dispatch_post(store, "/api/kos/update", {}, json.dumps({"id": t.id, "effort_h": "x"}).encode())[0] == 400
    st, res = dispatch(store, "/api/workload", {"days": "3"})
    assert st == 200 and len(res["days"]) == 3 and res["totals"]["tasks"] == 0
