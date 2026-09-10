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


# ── Entrega 3: proyectos especiales, semana, captura de correo ───────────

from datetime import date, timedelta

from segundo_cerebro.agents import save_latest_triage
from segundo_cerebro.mail_capture import capture_by_id, capture_email, email_to_note
from segundo_cerebro.priority import area_scores, signals_label
from segundo_cerebro.projects import (Milestone, Project, import_plan, load_projects,
                                      parse_plan_xlsx, project_brief, project_status,
                                      week_review)

PROJECTS_FILE = REPO / "brain" / "self" / "projects.md"


def _plan_xlsx(path: Path):
    from openpyxl import Workbook
    wb = Workbook()
    portada = wb.active
    portada.title = "Portada"
    portada.append(["", "PLAN DE TRABAJO"])
    portada.append(["", "Actividades Detalladas", "ver hoja"])   # no es cabecera
    ws = wb.create_sheet("Actividades Detalladas")
    ws.append(["ACTIVIDADES DETALLADAS DEL PLAN"])
    ws.append(["Fase", "Sem.", "Actividad", "Responsable", "Entregable", "Duración", "Estado", "Prioridad"])
    ws.append(["F1", "S1", "Búsqueda sistemática de literatura", "IP", "Lista ≥30 artículos", "5 días", "Completado", "Alta"])
    ws.append(["F1", "S2", "Entrevistas semiestructuradas", "IP", "10 transcripciones", "7 días", "Pendiente", "Alta"])
    ws.append(["F2", "S9", "Pruebas de usabilidad con prototipo", "IP + Part.", "Informe SUS", "4 días", "Pendiente", "Crítica"])
    wb.save(path)


def test_seed_projects_and_plan_parser(tmp_path):
    projects = load_projects(PROJECTS_FILE)
    assert projects and projects[0].id == "tesis" and projects[0].area == "academia"
    assert projects[0].milestones and projects[0].milestones[0].due.startswith("2026")

    xlsx = tmp_path / "plan.xlsx"
    _plan_xlsx(xlsx)
    rows = parse_plan_xlsx(xlsx, start="2026-04-06")
    assert [r["sheet"] for r in rows] == ["Actividades Detalladas"] * 3, "elige la hoja con actividades"
    assert rows[0]["due"] == "2026-04-12" and rows[0]["status"] == "done"
    assert rows[2]["week"] == 9 and rows[2]["due"] == "2026-06-07" and rows[2]["priority"] == "Crítica"
    assert parse_plan_xlsx(xlsx)[1]["due"] is None, "sin start no inventa fechas"


def test_import_plan_is_idempotent_and_feeds_today_and_priority(store, tmp_path):
    xlsx = tmp_path / "PlanTrabajo.xlsx"
    _plan_xlsx(xlsx)
    today = date.today()
    start = (today - timedelta(days=20)).isoformat()   # S1 y S2 ya vencieron, S9 no
    project = Project(id="tesis", name="MSc Thesis", area="academia", start=start,
                      deadline=(today + timedelta(days=60)).isoformat(),
                      milestones=[Milestone("Pruebas de usabilidad", (today + timedelta(days=10)).isoformat())],
                      people=["Inti"])
    res = import_plan(store, xlsx, project)
    assert res["tasks"] == 3 and res["dated"] == 3
    again = import_plan(store, xlsx, project)
    assert again["tasks"] == 3
    tasks = store.list_knowledge_objects(ko_type="task", project="MSc Thesis", limit=50)
    assert len(tasks) == 3, "reimportar reemplaza, no duplica"
    assert {t.status for t in tasks} == {"done", "active"}
    assert all(t.area == "academia" and t.source_doc == res["doc_id"] for t in tasks)
    assert store.get_document(res["doc_id"]).metadata["extractor"] == "PlanImporter"

    st = project_status(store, project, today)
    assert st["done"] == 1 and [t.title for t in st["overdue"]] == ["Entrevistas semiestructuradas"]
    assert st["next_milestone"].name == "Pruebas de usabilidad" and st["days_to_deadline"] == 60
    lines = project_brief(store, [project], today)
    assert lines[0].startswith("### MSc Thesis — entrega en 60 días")
    assert any("⚠ Atrasada" in l and "Entrevistas" in l for l in lines)

    scores = {r["id"]: r for r in area_scores(store, AREAS, tmp_path)}
    assert scores["academia"]["signals"]["overdue"] == 1
    assert "1 atrasadas" in signals_label(scores["academia"]["signals"])

    md = week_review(store, tmp_path, [project], {a.id: a.name for a in AREAS}, today)
    assert "## Revisión semanal" not in md and md.startswith("# Revisión semanal")
    assert "Atrasados: 1" in md and "Entrevistas semiestructuradas" in md
    assert "Pruebas de usabilidad" in md and "MSc Thesis" in md


def test_mail_capture_is_explicit_and_only_path_for_mail_text(store, tmp_path):
    email = {"id": "m-1", "account": "falp", "from": "Ricardo Morales <r@falp.org>",
             "to": "inti@falp.org", "subject": "Aprobación base oncohematológica",
             "date": "2026-09-08T10:00:00-03:00", "labels": [],
             "snippet": "Hola Inti, confirmo…",
             "body": "Hola Inti,\n\nDECISIÓN: aprobamos la base oncohematológica.\n\n- [ ] Enviar variables mínimas el viernes\n\nRicardo"}
    # el triaje persistido no lleva cuerpo ni snippet, pero sí id/cuenta
    save_latest_triage(tmp_path, [{**email, "priority": 1, "reasons": ["x"]}])
    saved = json.loads((tmp_path / "reports" / "latest-triage.json").read_text(encoding="utf-8"))
    assert saved[0]["id"] == "m-1" and saved[0]["account"] == "falp"
    assert "body" not in saved[0] and "snippet" not in saved[0]

    note = email_to_note(email)
    assert note.startswith("---\ntitle:") and "message_id: m-1" in note

    res = capture_email(store, tmp_path, email)
    assert not res["duplicate"] and res["kos"] >= 2 and res["area"] == "falp"
    path = Path(res["path"])
    assert path.parent == tmp_path / "captured" and path.name.startswith("2026-09-08-aprobacion")
    doc = store.get_document(res["doc_id"])
    assert doc.doc_type == "email" and doc.metadata["message_id"] == "m-1"
    assert any(k.ko_type == "decision" for k in store.list_knowledge_objects(limit=100)
               if k.source_doc == doc.id)
    assert capture_email(store, tmp_path, email)["duplicate"] is True

    fetched = []
    fake_fetch = lambda alias, mid: (fetched.append((alias, mid)) or
                                     ({**email, "id": "m-2", "subject": "Otro", "body": "Otro cuerpo"} if mid == "m-2" else None))
    res = capture_by_id(store, tmp_path, "falp", "m-2", fetch=fake_fetch)
    assert fetched == [("falp", "m-2")] and res["title"] == "Otro"
    assert "error" in capture_by_id(store, tmp_path, "falp", "nope", fetch=fake_fetch)


def test_api_week_projects_and_capture(store, tmp_path):
    st, res = dispatch(store, "/api/week", {})
    assert st == 200 and res["markdown"].startswith("# Revisión semanal")
    st, res = dispatch(store, "/api/projects", {})
    assert st == 200 and res[0]["id"] == "tesis" and "next_milestone" in res[0]

    email = {"id": "m-9", "account": "falp", "from": "Ana <a@x.cl>", "subject": "Minuta",
             "date": "2026-09-01T09:00:00Z", "body": "PREGUNTA: ¿quién valida el estándar?"}
    st, res = dispatch_post(store, "/api/mail/capture",
                            {"_fetch": lambda a, m: email if m == "m-9" else None},
                            json.dumps({"id": "m-9", "account": "falp"}).encode())
    assert st == 200 and res["kos"] >= 1 and (tmp_path / "captured").exists()
    st, res = dispatch_post(store, "/api/mail/capture",
                            {"_fetch": lambda a, m: None},
                            json.dumps({"id": "zz", "account": "falp"}).encode())
    assert st == 404
    st, res = dispatch_post(store, "/api/mail/capture", {}, b"{}")
    assert st == 400
