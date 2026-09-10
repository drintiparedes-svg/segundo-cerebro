"""Modo activo — Entrega 1: config, asesor de fuentes, personas fijadas.
Todo local, sin red."""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro.advisor import (apply_suggestion, candidate_roots,
                                     drive_query_suggestions, scan_folder,
                                     score_folder, suggest_sources)
from segundo_cerebro.agents.mail_triage import heuristic_triage
from segundo_cerebro.areas import Area, assign_all, load_areas
from segundo_cerebro.config import (DEFAULTS, llm_areas, load_config,
                                    save_config, set_llm_areas)
from segundo_cerebro.connectors.localfs import load_registry
from segundo_cerebro.ingest import ingest_path
from segundo_cerebro.people import (key_people_brief, load_people_overrides,
                                    people_scores, pinned_names,
                                    set_person_override)
from segundo_cerebro.store import BrainStore
from segundo_cerebro.today import build_today
from segundo_cerebro.webapi import dispatch, dispatch_post

REPO = Path(__file__).resolve().parents[1]
AREAS = load_areas(REPO / "brain" / "self" / "areas.md")
SAMPLE = REPO / "brain" / "inbox" / "2026-08-12-reunion-oncohematologia.md"


@pytest.fixture()
def store(tmp_path):
    s = BrainStore(tmp_path / "b.db")
    ingest_path(s, SAMPLE, prefer_llm=False)
    assign_all(s, AREAS)
    yield s
    s.close()


# ── config ────────────────────────────────────────────────────────────────

def test_config_defaults_and_never_wins(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg["llm"]["default"] == "local" and "clinica" in cfg["llm"]["never"]
    assert cfg == DEFAULTS and cfg is not DEFAULTS
    set_llm_areas(tmp_path, ["academia", "falp"])
    assert llm_areas(load_config(tmp_path)) == ["academia", "falp"]
    with pytest.raises(ValueError):
        set_llm_areas(tmp_path, ["clinica"])
    cfg = load_config(tmp_path)
    cfg["refresh"]["every_hours"] = 2
    save_config(tmp_path, cfg)
    again = load_config(tmp_path)
    assert again["refresh"]["every_hours"] == 2 and again["refresh"]["triage_days"] == 7


# ── asesor de fuentes ─────────────────────────────────────────────────────

def _make_tree(root: Path):
    tesis = root / "Tesis 2026"
    tesis.mkdir()
    for i in range(6):
        (tesis / f"self-sampling-hpv-{i}.docx").write_bytes(b"x")
    (tesis / "PlanTrabajo_VPH.xlsx").write_bytes(b"x")
    fotos = root / "Fotos"
    fotos.mkdir()
    for i in range(30):
        (fotos / f"IMG_{i}.jpg").write_bytes(b"x")
    old = root / "Antiguo"
    old.mkdir()
    for i in range(3):
        p = old / f"nota{i}.txt"
        p.write_text("x")
        os.utime(p, (time.time() - 400 * 86400, time.time() - 400 * 86400))
    (root / "node_modules").mkdir()
    return tesis, fotos, old


def test_advisor_scans_without_opening_files_and_scores(tmp_path):
    tesis, fotos, old = _make_tree(tmp_path)
    stats = scan_folder(tesis, AREAS)
    assert stats["supported"] == 7 and stats["recent"] == 7
    assert stats["area_guess"] == "academia", stats["area_hits"]
    score, verdict, reasons = score_folder(stats)
    assert verdict == "conectar" and score > 0
    assert score_folder(scan_folder(fotos, AREAS))[1] == "ignorar"
    assert score_folder(scan_folder(old, AREAS))[1] == "revisar"


def test_suggest_apply_and_remember(tmp_path):
    brain = tmp_path / ".brain"
    root = tmp_path / "Escritorio"
    root.mkdir()
    _make_tree(root)
    sugg = suggest_sources(brain, [root], AREAS)
    names = [s["name"] for s in sugg]
    assert names[0] == "Tesis 2026" and "node_modules" not in names
    assert sugg[0]["verdict"] == "conectar" and sugg[-1]["verdict"] == "ignorar"

    done = apply_suggestion(brain, root / "Tesis 2026", accept=True)
    assert done["action"] == "conectada"
    apply_suggestion(brain, root / "Fotos", accept=False)
    reg = load_registry(brain)
    assert reg["sources"][0]["alias"] == "Tesis 2026"
    assert str((root / "Fotos").resolve()) in reg["ignored"]
    assert reg.get("suggested_at")

    again = [s["name"] for s in suggest_sources(brain, [root], AREAS)]
    assert "Tesis 2026" not in again and "Fotos" not in again, "recuerda decisiones"
    # nada escrito dentro de las carpetas: solo .brain/sources.json
    assert sorted(p.name for p in (root / "Tesis 2026").iterdir()) == sorted(
        [f"self-sampling-hpv-{i}.docx" for i in range(6)] + ["PlanTrabajo_VPH.xlsx"])


def test_candidate_roots_and_drive_queries(tmp_path):
    (tmp_path / "Documentos").mkdir()
    (tmp_path / "Descargas").mkdir()
    desk = tmp_path / "Escritorio"
    desk.mkdir()
    roots = candidate_roots(desk, home=tmp_path)
    assert roots[0] == desk and {r.name for r in roots[1:]} == {"Documentos", "Descargas"}
    q = drive_query_suggestions([Area(id="academia", name="Academia",
                                      keywords=["hpv", "self-sampling"],
                                      projects=["MSc Thesis"])])
    assert q[0]["area"] == "academia" and "name contains 'MSc Thesis'" in q[0]["query"]


# ── personas fijadas ──────────────────────────────────────────────────────

def test_people_ranking_pin_and_suggestion(store, tmp_path):
    data = people_scores(store, tmp_path)
    names = [p["name"] for p in data["people"]]
    assert "Ricardo" in names
    top = data["people"][0]
    assert top["score"] > 0 and not top["pinned"]

    entry = set_person_override(tmp_path, "Ricardo", pin=True, role="Gerente", area="falp")
    assert entry["pin"] and pinned_names(tmp_path) == ["Ricardo"]
    data = people_scores(store, tmp_path)
    assert data["people"][0]["name"] == "Ricardo", "el pin manda sobre el score"
    assert data["people"][0]["role"] == "Gerente"
    assert "Ricardo" not in data["suggested"]

    set_person_override(tmp_path, "Ricardo", pin=False)
    assert load_people_overrides(tmp_path)["Ricardo"]["role"] == "Gerente", "el rol se conserva"
    assert pinned_names(tmp_path) == []
    set_person_override(tmp_path, "Inti", pin=True)
    set_person_override(tmp_path, "Inti", pin=False)
    assert "Inti" not in load_people_overrides(tmp_path), "sin pin ni datos → se limpia"


def test_pinned_sender_gets_priority_in_triage(store, tmp_path):
    mails = [{"id": "m1", "from": "Ricardo Morales <r@falp.org>",
              "subject": "hola", "snippet": "", "labels": []},
             {"id": "m2", "from": "Desconocido <x@y.cl>",
              "subject": "hola", "snippet": "", "labels": []}]
    before = {m["id"]: m["score"] for m in heuristic_triage(mails, store)}
    set_person_override(tmp_path, "Ricardo", pin=True)
    after = {m["id"]: m for m in heuristic_triage(mails, store)}
    assert after["m1"]["score"] == before["m1"] + 30
    assert "persona fijada por ti" in after["m1"]["reasons"]
    assert after["m2"]["score"] == before["m2"]


def test_key_people_in_brief_and_unknown_senders(store, tmp_path):
    set_person_override(tmp_path, "Ricardo", pin=True, role="Gerente clínico")
    lines = key_people_brief(store, tmp_path)
    assert lines[0].startswith("### 📌 Ricardo — Gerente clínico")
    brief = build_today(store, tmp_path, AREAS)
    assert "## Personas clave" in brief and "📌 Ricardo" in brief

    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "latest-triage.json").write_text(json.dumps([
        {"priority": 2, "from": "Ana Soto <ana@imperial.ac.uk>", "subject": "s"},
        {"priority": 3, "from": "Ana Soto <ana@imperial.ac.uk>", "subject": "s"},
        {"priority": 1, "from": "Ricardo <r@falp.org>", "subject": "s"},
    ]), encoding="utf-8")
    data = people_scores(store, tmp_path)
    assert data["unknown_senders"][0] == {"name": "Ana Soto", "mails": 2}
    ricardo = next(p for p in data["people"] if p["name"] == "Ricardo")
    assert ricardo["signals"]["mail"] == 1


# ── API ───────────────────────────────────────────────────────────────────

def test_api_people_sources_today(store, tmp_path):
    status, people = dispatch(store, "/api/people", {})
    assert status == 200 and people["people"] and "signals_label" in people["people"][0]

    status, res = dispatch_post(store, "/api/people/pin", {},
                                json.dumps({"name": "Ricardo", "pin": True}).encode())
    assert status == 200 and res["people"][0]["name"] == "Ricardo"
    _, graph = dispatch(store, "/api/graph", {})
    assert any(n.get("pinned") for n in graph["nodes"] if n["name"] == "Ricardo")

    folder = tmp_path / "Proyectos"
    folder.mkdir()
    (folder / "plan.md").write_text("# plan")
    status, res = dispatch_post(store, "/api/sources/apply", {},
                                json.dumps({"path": str(folder), "accept": True}).encode())
    assert status == 200 and res["sources"][0]["alias"] == "Proyectos"
    assert res["sources"][0]["available"] is True

    status, res = dispatch(store, "/api/sources/suggest", {"root": str(tmp_path)})
    assert status == 200 and all(s["name"] != "Proyectos" for s in res["suggestions"])

    status, res = dispatch(store, "/api/today", {})
    assert status == 200 and res["markdown"].startswith("# Tu día")


# ── Entrega 2: enrich por área, refresh, schedule ─────────────────────────

from segundo_cerebro import scheduler
from segundo_cerebro.enrich import enrich
from segundo_cerebro.extract import ExtractionResult, HeuristicExtractor
from segundo_cerebro.models import KnowledgeObject, new_id
from segundo_cerebro.refresh import (STEPS, is_locked, last_refresh, lock_path,
                                     run_refresh, status)


class ClaudeExtractor:
    """Doble de prueba con el mismo nombre de clase que el real: así el
    marcador `extractor` en metadata se comporta igual que en producción."""

    def extract(self, doc):
        return ExtractionResult(knowledge_objects=[KnowledgeObject(
            id=new_id("ko"), ko_type="decision", title="Semántica",
            statement=f"Decisión semántica extraída de {doc.title}",
            date=doc.date, people=["Ricardo"], source_doc=doc.id)])


def test_enrich_replaces_heuristic_kos_only_in_allowed_areas(store, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    doc = store.list_documents()[0]
    assert doc.metadata["extractor"] == "HeuristicExtractor"
    before = store.list_knowledge_objects(limit=100)
    assert before and all(k.source_doc == doc.id for k in before)

    assert enrich(store, tmp_path)["skipped"].startswith("sin áreas")
    set_llm_areas(tmp_path, ["falp"])
    assert "sin credenciales" in enrich(store, tmp_path)["skipped"]
    assert enrich(store, tmp_path, areas=["clinica"])["skipped"].startswith("área(s) prohibida")
    dry = enrich(store, tmp_path, dry_run=True)
    assert dry["pending"] == 1 and dry["docs"][0]["area"] == "falp"

    result = enrich(store, tmp_path, extractor=ClaudeExtractor())
    assert result["enriched"] == 1 and result["removed"]["kos"] == len(before)
    after = store.list_knowledge_objects(limit=100)
    assert len(after) == 1 and after[0].statement.startswith("Decisión semántica")
    assert after[0].area == "falp", "la clasificación por área se re-aplica"
    assert store.get_document(doc.id).metadata["extractor"] == "ClaudeExtractor"
    assert enrich(store, tmp_path, extractor=ClaudeExtractor())["enriched"] == 0, "idempotente"


def test_refresh_runs_steps_in_order_tolerates_errors_and_locks(store, tmp_path):
    order = []

    def ok(name):
        def run(store, brain_dir, cfg):
            order.append(name)
            return {"n": 1}
        return run

    def boom(store, brain_dir, cfg):
        order.append("google")
        raise RuntimeError("sin red")

    runners = {"sources": ok("sources"), "google": boom, "mail": ok("mail"),
               "areas": ok("areas"), "enrich": ok("enrich"), "brief": ok("brief")}
    state = run_refresh(store, tmp_path, runners=runners, skip=["mail"])
    assert order == ["sources", "google", "areas", "enrich", "brief"]
    assert state["ok"] is False and state["steps"]["google"]["error"].startswith("RuntimeError")
    assert state["steps"]["mail"]["skipped"] == "omitido"
    assert state["steps"]["sources"]["n"] == 1 and state["duration_s"] >= 0
    assert last_refresh(tmp_path)["started"] == state["started"]
    assert not is_locked(tmp_path) and list((tmp_path / "logs").glob("refresh-*.log"))

    lock_path(tmp_path).write_text("pid")
    assert run_refresh(store, tmp_path, runners=runners)["locked"] is True
    lock_path(tmp_path).unlink()

    st = status(store, tmp_path)
    assert st["running"] is False and st["counts"]["documents"] == 1
    assert st["minutes_ago"] == 0 and st["next_due"]


def test_refresh_default_runners_without_connectors(store, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    state = run_refresh(store, tmp_path)
    assert state["ok"] is True
    assert state["steps"]["sources"]["skipped"] and state["steps"]["google"]["skipped"]
    assert state["steps"]["areas"]["documents"] == 1
    assert "sin" in state["steps"]["enrich"]["skipped"]
    assert Path(state["steps"]["brief"]["path"]).exists()
    assert (tmp_path / "state" / "latest-brief.md").read_text(encoding="utf-8").startswith("# Tu día")


def test_scheduler_plans_per_platform(tmp_path):
    assert scheduler.parse_every("4h") == 240 and scheduler.parse_every("90m") == 90
    assert scheduler.parse_every(2) == 120 and scheduler.parse_every("5m") == 15
    with pytest.raises(ValueError):
        scheduler.parse_every("cada rato")
    proj, db = tmp_path / "proj", str(tmp_path / "proj" / ".brain" / "brain.db")
    win = scheduler.install(proj, db, "4h", platform="win32", python="py.exe", dry_run=True)
    assert win["platform"] == "windows" and win["commands"][0][:2] == ["schtasks", "/Create"]
    assert "/MO" in win["commands"][0] and "240" in win["commands"][0]
    assert any("ONLOGON" in c for c in win["commands"][1])
    mac = scheduler.install(proj, db, "2h", platform="darwin", python="/usr/bin/python3",
                            home=tmp_path, dry_run=True)
    assert mac["plist"]["StartInterval"] == 7200 and mac["plist"]["RunAtLoad"]
    assert mac["plist"]["ProgramArguments"][-2:] == ["refresh", "--quiet"]
    assert mac["plist_path"].startswith(str(tmp_path))
    lin = scheduler.install(proj, db, "4h", platform="linux", python="/usr/bin/python3", dry_run=True)
    assert lin["cron_line"].startswith("0 */4 * * * cd ") and lin["cron_line"].endswith(scheduler.CRON_TAG)
    assert scheduler.remove(platform="darwin", home=tmp_path, dry_run=True)["removed"] is False
    assert scheduler.status(platform="darwin", home=tmp_path)["installed"] is False


def test_desktop_shortcut_refreshes_before_serving(tmp_path, monkeypatch):
    from segundo_cerebro.desktop import create_shortcut
    monkeypatch.setattr(sys, "platform", "linux")
    path = create_shortcut(tmp_path, tmp_path / "proj")
    text = path.read_text(encoding="utf-8")
    assert "refresh --quiet" in text and text.index("refresh") < text.index("serve")
    monkeypatch.setattr(sys, "platform", "win32")
    text = create_shortcut(tmp_path, tmp_path / "proj").read_text(encoding="utf-8")
    assert "refresh --quiet" in text and "serve --port" in text


def test_api_status_config_and_refresh(store, tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    st, res = dispatch(store, "/api/status", {})
    assert st == 200 and res["last"] is None and res["running"] is False
    st, res = dispatch(store, "/api/config", {})
    assert res["config"]["llm"]["never"] == ["clinica"] and any(a["id"] == "falp" for a in res["areas"])

    st, res = dispatch_post(store, "/api/config/llm", {}, json.dumps({"areas": ["clinica"]}).encode())
    assert st == 403
    st, res = dispatch_post(store, "/api/config/llm", {}, json.dumps({"areas": ["academia"]}).encode())
    assert st == 200 and res["config"]["llm"]["areas"] == ["academia"]

    from segundo_cerebro import webapi
    st, res = dispatch_post(store, "/api/refresh", {}, b"{}")
    assert st == 200 and res["started"] is True
    webapi._refresh_threads[str(tmp_path)].join(timeout=30)
    st, res = dispatch(store, "/api/status", {})
    assert res["running"] is False and res["last"]["ok"] is True and res["minutes_ago"] == 0
