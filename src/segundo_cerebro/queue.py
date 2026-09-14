"""Bandeja de aprobación y registro de acciones.

Los agentes no actúan: **proponen** ítems. Según la matriz de autonomía el
ítem se ejecuta de inmediato (L3/L3+, con deshacer), espera tu aprobación
(L2) o queda como sugerencia (L1). Todo queda en `.brain/queue/` y en
`.brain/logs/actions.log`. Los ejecutores son los únicos que tocan algo:
un archivo en .brain/drafts, un evento en TU calendario, un borrador en TU
Gmail — siempre reversibles con `undo`.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import new_id

STATUSES = ("pending", "suggested", "executed", "rejected", "undone", "failed", "manual")


def queue_dir(brain_dir: str | Path) -> Path:
    d = Path(brain_dir) / "queue"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _log(brain_dir: Path, line: str) -> None:
    logs = brain_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / "actions.log").open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {line}\n")


def _save(brain_dir: Path, item: dict) -> dict:
    (queue_dir(brain_dir) / f"{item['id']}.json").write_text(
        json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    return item


def list_items(brain_dir: str | Path, status: str | None = None) -> list[dict]:
    items = []
    for p in queue_dir(brain_dir).glob("*.json"):
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    if status:
        items = [i for i in items if i.get("status") == status]
    return sorted(items, key=lambda i: i.get("created_at", ""), reverse=True)


def get_item(brain_dir: str | Path, item_id: str) -> dict | None:
    p = queue_dir(brain_dir) / f"{item_id}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def exists(brain_dir: str | Path, key: str) -> bool:
    """¿Ya hay un ítem con esa clave (no rechazado ni deshecho)?"""
    return any(i.get("key") == key and i.get("status") in ("pending", "suggested", "executed", "manual", "failed")
               for i in list_items(brain_dir))


# ── ejecutores ────────────────────────────────────────────────────────────

def _exec_draft_note(payload: dict, brain_dir: Path, store) -> dict:
    from .agents.writer import save_draft
    path = save_draft(brain_dir, payload.get("kind", "nota"), payload["markdown"])
    return {"path": str(path), "undo": {"path": str(path)}}


def _undo_draft_note(result: dict, brain_dir: Path, store) -> None:
    Path(result["undo"]["path"]).unlink(missing_ok=True)


def _exec_calendar_block(payload: dict, brain_dir: Path, store) -> dict:
    from .connectors.google_write import create_event
    ev = create_event(payload["account"], payload["summary"], payload["start"], payload["end"],
                      description=payload.get("description", ""), base=brain_dir / "google")
    return {"event_id": ev["id"], "html_link": ev.get("htmlLink"),
            "undo": {"account": payload["account"], "event_id": ev["id"]}}


def _undo_calendar_block(result: dict, brain_dir: Path, store) -> None:
    from .connectors.google_write import delete_event
    delete_event(result["undo"]["account"], result["undo"]["event_id"], base=brain_dir / "google")


def _exec_gmail_draft(payload: dict, brain_dir: Path, store) -> dict:
    from .connectors.google_write import create_draft
    d = create_draft(payload["account"], payload["to"], payload["subject"], payload["body"],
                     base=brain_dir / "google", thread_id=payload.get("thread_id"))
    return {"draft_id": d["id"], "undo": {"account": payload["account"], "draft_id": d["id"]}}


def _undo_gmail_draft(result: dict, brain_dir: Path, store) -> None:
    from .connectors.google_write import delete_draft
    delete_draft(result["undo"]["account"], result["undo"]["draft_id"], base=brain_dir / "google")


def _exec_weekly_review(payload: dict, brain_dir: Path, store) -> dict:
    from .agents import save_report
    from .areas import load_areas
    from .projects import load_projects, week_review
    names = {a.id: a.name for a in load_areas()}
    md = week_review(store, brain_dir, load_projects(), names)
    path = save_report(brain_dir, "semana", md)
    return {"path": str(path), "undo": {"path": str(path)}}


EXECUTORS = {
    "draft_note": (_exec_draft_note, _undo_draft_note),
    "calendar_block": (_exec_calendar_block, _undo_calendar_block),
    "gmail_draft": (_exec_gmail_draft, _undo_gmail_draft),
    "weekly_review": (_exec_weekly_review, _undo_draft_note),
}
MANUAL_HINTS = {
    "calendar_block": "crea tú el bloque en tu calendario (o autoriza escritura: sb google connect <alias> --write)",
    "gmail_draft": "crea tú el borrador en Gmail (o autoriza escritura: sb google connect <alias> --write)",
}


# ── ciclo de vida ─────────────────────────────────────────────────────────

def submit(brain_dir: str | Path, store, action: str, executor: str, title: str,
           payload: dict, rationale: str = "", key: str | None = None,
           source_doc: str | None = None, decision: str | None = None) -> dict:
    """Crea el ítem y lo resuelve según la matriz de autonomía."""
    from .autonomy import decide, effective_level
    brain_dir = Path(brain_dir)
    if key and exists(brain_dir, key):
        return {"duplicate": True, "key": key}
    decision = decision or decide(brain_dir, action)
    item = {"id": new_id("act"), "action": action, "executor": executor, "title": title,
            "payload": payload, "rationale": rationale, "key": key, "source_doc": source_doc,
            "level": effective_level(brain_dir, action), "decision": decision,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "status": "pending", "result": None, "resolved_at": None}
    if decision == "suggest":
        item["status"] = "suggested"
        _save(brain_dir, item)
        _log(brain_dir, f"SUGERIDO {item['id']} {action}: {title}")
        return item
    if decision == "auto":
        _save(brain_dir, item)
        return execute(brain_dir, store, item["id"])
    _save(brain_dir, item)
    _log(brain_dir, f"EN BANDEJA {item['id']} {action}: {title}")
    return item


def execute(brain_dir: str | Path, store, item_id: str) -> dict:
    brain_dir = Path(brain_dir)
    item = get_item(brain_dir, item_id)
    if item is None:
        raise KeyError(f"no existe el ítem {item_id}")
    executor = EXECUTORS.get(item["executor"])
    if executor is None:
        item.update({"status": "manual", "resolved_at": datetime.now().isoformat(timespec="seconds"),
                     "result": {"hint": "sin ejecutor: hazlo tú con los datos del ítem"}})
        _log(brain_dir, f"MANUAL {item['id']} {item['action']}: {item['title']}")
        return _save(brain_dir, item)
    try:
        result = executor[0](item["payload"], brain_dir, store)
        item.update({"status": "executed", "result": result,
                     "resolved_at": datetime.now().isoformat(timespec="seconds")})
        _log(brain_dir, f"EJECUTADO {item['id']} {item['action']}: {item['title']} → {json.dumps(result.get('undo', {}), ensure_ascii=False)}")
    except Exception as exc:
        hint = MANUAL_HINTS.get(item["executor"], "")
        item.update({"status": "manual" if hint else "failed",
                     "result": {"error": f"{type(exc).__name__}: {exc}", "hint": hint},
                     "resolved_at": datetime.now().isoformat(timespec="seconds")})
        _log(brain_dir, f"{'MANUAL' if hint else 'FALLÓ'} {item['id']} {item['action']}: {exc}")
    return _save(brain_dir, item)


def approve(brain_dir: str | Path, store, item_id: str) -> dict:
    item = get_item(brain_dir, item_id)
    if item is None:
        raise KeyError(f"no existe el ítem {item_id}")
    if item["status"] not in ("pending", "suggested", "failed"):
        return item
    _log(Path(brain_dir), f"APROBADO {item_id} por el usuario")
    return execute(brain_dir, store, item_id)


def reject(brain_dir: str | Path, item_id: str, reason: str = "") -> dict:
    brain_dir = Path(brain_dir)
    item = get_item(brain_dir, item_id)
    if item is None:
        raise KeyError(f"no existe el ítem {item_id}")
    item.update({"status": "rejected", "resolved_at": datetime.now().isoformat(timespec="seconds"),
                 "result": {"reason": reason}})
    _log(brain_dir, f"RECHAZADO {item_id}: {reason or '—'}")
    return _save(brain_dir, item)


def undo(brain_dir: str | Path, store, item_id: str) -> dict:
    brain_dir = Path(brain_dir)
    item = get_item(brain_dir, item_id)
    if item is None:
        raise KeyError(f"no existe el ítem {item_id}")
    if item["status"] != "executed" or not (item.get("result") or {}).get("undo"):
        return item
    executor = EXECUTORS.get(item["executor"])
    if executor and executor[1]:
        executor[1](item["result"], brain_dir, store)
    item.update({"status": "undone", "resolved_at": datetime.now().isoformat(timespec="seconds")})
    _log(brain_dir, f"DESHECHO {item_id} {item['action']}")
    return _save(brain_dir, item)


def summary(brain_dir: str | Path) -> dict:
    items = list_items(brain_dir)
    return {s: sum(1 for i in items if i.get("status") == s) for s in STATUSES}
