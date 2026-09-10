"""`sb refresh`: un solo comando que mantiene el cerebro al día.

Orden: fuentes locales → Google (Calendar + Drive) → triaje de correo
(metadatos) → clasificación por área → enriquecimiento con Claude (solo
áreas permitidas) → brief del día. Cada paso tolera fallos: un conector
caído no detiene a los demás. Nada sale del equipo salvo lo que ya salía
(Google de solo lectura; Claude si lo habilitaste por área).

Deja huella en .brain/state/last_refresh.json y .brain/logs/, y usa un
lock para no solaparse con el servicio programado.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from .config import load_config

STEPS = ["sources", "google", "mail", "areas", "enrich", "brief"]
LOCK_STALE_HOURS = 2


def state_dir(brain_dir: str | Path) -> Path:
    d = Path(brain_dir) / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def lock_path(brain_dir: str | Path) -> Path:
    return state_dir(brain_dir) / "refresh.lock"


def is_locked(brain_dir: str | Path) -> bool:
    lock = lock_path(brain_dir)
    if not lock.exists():
        return False
    age = time.time() - lock.stat().st_mtime
    if age > LOCK_STALE_HOURS * 3600:
        lock.unlink(missing_ok=True)   # lock huérfano de un proceso caído
        return False
    return True


def last_refresh(brain_dir: str | Path) -> dict | None:
    path = state_dir(brain_dir) / "last_refresh.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _log(brain_dir: Path, line: str) -> None:
    logs = brain_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with (logs / f"refresh-{datetime.now():%Y%m%d}.log").open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {line}\n")


# ── pasos por defecto ─────────────────────────────────────────────────────

def _step_sources(store, brain_dir: Path, cfg: dict) -> dict:
    from .connectors.localfs import load_registry, sync_source
    from .extract import HeuristicExtractor
    from .ingest import new_summary, process_document
    registry = load_registry(brain_dir)
    if not registry["sources"]:
        return {"skipped": "sin carpetas conectadas"}
    extractor = HeuristicExtractor()
    summary = new_summary(extractor)
    per_source = {}
    for source in registry["sources"]:
        result = sync_source(store, brain_dir, source)
        if "error" in result:
            per_source[source["alias"]] = {"error": result["error"]}
            continue
        for doc in result["docs"]:
            summary["documents"] += 1
            process_document(store, doc, extractor, summary)
        per_source[source["alias"]] = {"added": result["added"]}
    return {"documents": summary["documents"], "kos": summary["knowledge_objects"],
            "sources": per_source}


def _step_google(store, brain_dir: Path, cfg: dict) -> dict:
    from .connectors.google_auth import list_accounts
    base = brain_dir / "google"
    accounts = list_accounts(base)
    if not accounts:
        return {"skipped": "sin cuentas Google conectadas"}
    from .connectors.google_sync import sync_all
    r = cfg["refresh"]
    summary = sync_all(store, accounts=accounts, days_back=r["days_back"],
                       days_forward=r["days_forward"], prefer_llm=False, base=base)
    return {"documents": summary["documents"], "kos": summary["knowledge_objects"],
            "accounts": summary["accounts"]}


def _step_mail(store, brain_dir: Path, cfg: dict) -> dict:
    from .agents import save_latest_triage, save_report
    from .agents.mail_triage import to_markdown, triage
    from .connectors.gmail import fetch_inbox
    from .connectors.google_auth import list_accounts
    base = brain_dir / "google"
    accounts = list_accounts(base)
    if not accounts:
        return {"skipped": "sin cuentas Google conectadas"}
    emails, errors = [], {}
    for alias in accounts:
        try:
            emails.extend(fetch_inbox(alias, days=cfg["refresh"]["triage_days"], base=base))
        except Exception as exc:
            errors[alias] = str(exc)
    if not emails:
        return {"mails": 0, "errors": errors}
    triaged = triage(emails, store, prefer_llm=False)   # metadatos, 100% local
    save_report(brain_dir, "triaje-correo", to_markdown(triaged))
    save_latest_triage(brain_dir, triaged)
    return {"mails": len(triaged),
            "p1_p2": sum(1 for m in triaged if m["priority"] <= 2), "errors": errors}


def _step_areas(store, brain_dir: Path, cfg: dict) -> dict:
    from .areas import assign_all, load_areas
    areas = load_areas()
    if not areas:
        return {"skipped": "sin brain/self/areas.md"}
    return assign_all(store, areas)


def _step_enrich(store, brain_dir: Path, cfg: dict) -> dict:
    from .enrich import enrich
    return enrich(store, brain_dir)


def _step_brief(store, brain_dir: Path, cfg: dict) -> dict:
    from .agents import save_report
    from .areas import load_areas
    from .today import build_today
    brief = build_today(store, brain_dir, load_areas())
    path = save_report(brain_dir, "brief", brief)
    (state_dir(brain_dir) / "latest-brief.md").write_text(brief, encoding="utf-8")
    return {"path": str(path)}


DEFAULT_RUNNERS = {
    "sources": _step_sources, "google": _step_google, "mail": _step_mail,
    "areas": _step_areas, "enrich": _step_enrich, "brief": _step_brief,
}


def run_refresh(store, brain_dir: str | Path, skip: list[str] | None = None,
                runners: dict | None = None, log=None) -> dict:
    """Ejecuta los pasos en orden. Devuelve el estado guardado en
    last_refresh.json. Si hay otro refresh en curso, devuelve
    {"locked": True} sin hacer nada."""
    brain_dir = Path(brain_dir)
    runners = runners or DEFAULT_RUNNERS
    skip = set(skip or [])
    if is_locked(brain_dir):
        return {"locked": True, "last": last_refresh(brain_dir)}
    lock = lock_path(brain_dir)
    lock.write_text(f"{os.getpid()} {datetime.now().isoformat()}", encoding="utf-8")
    cfg = load_config(brain_dir)
    started = datetime.now()
    state = {"started": started.isoformat(timespec="seconds"), "steps": {}}
    say = log or (lambda msg: None)
    try:
        for name in STEPS:
            if name in skip or name not in runners:
                state["steps"][name] = {"ok": True, "skipped": "omitido"}
                continue
            t0 = time.time()
            try:
                result = runners[name](store, brain_dir, cfg)
                entry = {"ok": True, "seconds": round(time.time() - t0, 1), **(result or {})}
            except Exception as exc:   # un paso caído no detiene el resto
                entry = {"ok": False, "seconds": round(time.time() - t0, 1),
                         "error": f"{type(exc).__name__}: {exc}"}
            state["steps"][name] = entry
            summary = entry.get("error") or entry.get("skipped") or \
                ", ".join(f"{k}={v}" for k, v in entry.items()
                          if k not in ("ok", "seconds") and not isinstance(v, dict))
            _log(brain_dir, f"{name}: {'ok' if entry['ok'] else 'ERROR'} "
                            f"({entry['seconds']}s) {summary}")
            say(f"{name:<8} {'✔' if entry['ok'] else '✘'} {summary}")
    finally:
        lock.unlink(missing_ok=True)
    finished = datetime.now()
    state["finished"] = finished.isoformat(timespec="seconds")
    state["duration_s"] = round((finished - started).total_seconds(), 1)
    state["ok"] = all(s["ok"] for s in state["steps"].values())
    (state_dir(brain_dir) / "last_refresh.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def status(store, brain_dir: str | Path) -> dict:
    """Estado para la UI: última sincronización, si hay una en curso, cuenta
    de la memoria y política LLM."""
    brain_dir = Path(brain_dir)
    last = last_refresh(brain_dir)
    cfg = load_config(brain_dir)
    minutes = None
    if last and last.get("finished"):
        minutes = int((datetime.now() - datetime.fromisoformat(last["finished"]))
                      .total_seconds() // 60)
    counts = {"documents": 0, "kos": 0}
    try:
        counts["documents"] = store.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        counts["kos"] = store.conn.execute("SELECT COUNT(*) FROM knowledge_objects").fetchone()[0]
    except Exception:
        pass
    return {"running": is_locked(brain_dir), "last": last, "minutes_ago": minutes,
            "counts": counts, "llm": cfg["llm"], "refresh": cfg["refresh"],
            "next_due": (datetime.fromisoformat(last["finished"])
                         + timedelta(hours=cfg["refresh"]["every_hours"])
                         ).isoformat(timespec="minutes") if last and last.get("finished") else None}
