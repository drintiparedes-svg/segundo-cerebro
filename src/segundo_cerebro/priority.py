"""Prioridad de áreas: jerarquía automática + validación manual.

El score se calcula 100% localmente a partir de señales de la memoria;
la validación manual (peso, pin, pausa) vive en .brain/area_overrides.json
y siempre gana sobre el cálculo automático.

    score_auto = tareas_abiertas×3 + eventos_7d×4 + decisiones_14d×2
               + preguntas×1 + correo_P1P2×4
    score      = score_auto × weight
    orden      = [pineadas por pin asc] + [resto por score desc] + [pausadas]
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .areas import Area, classify

WEIGHTS = {"tasks": 3, "events": 4, "decisions": 2, "questions": 1, "mail": 4}


# ── overrides manuales ────────────────────────────────────────────────────

def _overrides_path(brain_dir: str | Path) -> Path:
    return Path(brain_dir) / "area_overrides.json"


def load_overrides(brain_dir: str | Path) -> dict:
    path = _overrides_path(brain_dir)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def set_override(brain_dir: str | Path, area_id: str, weight: float | None = None,
                 pin: int | None = None, unpin: bool = False,
                 status: str | None = None) -> dict:
    overrides = load_overrides(brain_dir)
    entry = overrides.setdefault(area_id, {})
    if weight is not None:
        entry["weight"] = max(0.1, float(weight))
    if unpin:
        entry.pop("pin", None)
    elif pin is not None:
        entry["pin"] = int(pin)
    if status in ("activa", "pausada"):
        entry["status"] = status
    path = _overrides_path(brain_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return entry


# ── señales y score ───────────────────────────────────────────────────────

def _mail_hits_by_area(brain_dir: str | Path, areas: list[Area]) -> dict[str, int]:
    """Correos P1-P2 del último triaje, clasificados por área (local)."""
    path = Path(brain_dir) / "reports" / "latest-triage.json"
    hits: dict[str, int] = {}
    if not path.exists():
        return hits
    for mail in json.loads(path.read_text(encoding="utf-8")):
        if mail.get("priority", 5) > 2:
            continue
        area = classify(f"{mail.get('subject', '')} {mail.get('from', '')}",
                        [], None, areas)
        if area:
            hits[area] = hits.get(area, 0) + 1
    return hits


def area_scores(store, areas: list[Area], brain_dir: str | Path) -> list[dict]:
    today = date.today()
    soon = str(today + timedelta(days=7))
    recent = str(today - timedelta(days=14))
    overrides = load_overrides(brain_dir)
    mail_hits = _mail_hits_by_area(brain_dir, areas)

    rows = []
    for area in areas:
        tasks = store.list_knowledge_objects(ko_type="task", status="active",
                                             area=area.id, limit=500)
        events = [e for e in store.list_knowledge_objects(
            ko_type="event", area=area.id, limit=500)
            if str(today) <= e.date <= soon]
        decisions = [d for d in store.list_knowledge_objects(
            ko_type="decision", area=area.id, limit=500) if d.date >= recent]
        questions = store.list_knowledge_objects(ko_type="question",
                                                 status="active",
                                                 area=area.id, limit=500)
        signals = {"tasks": len(tasks), "events": len(events),
                   "decisions": len(decisions), "questions": len(questions),
                   "mail": mail_hits.get(area.id, 0)}
        auto = sum(signals[k] * WEIGHTS[k] for k in WEIGHTS)

        ov = overrides.get(area.id, {})
        weight = float(ov.get("weight", 1.0))
        rows.append({
            "id": area.id, "name": area.name,
            "score": round(auto * weight, 1), "score_auto": auto,
            "signals": signals, "weight": weight,
            "pin": ov.get("pin"), "status": ov.get("status", "activa"),
        })

    pinned = sorted([r for r in rows if r["pin"] is not None and r["status"] != "pausada"],
                    key=lambda r: r["pin"])
    active = sorted([r for r in rows if r["pin"] is None and r["status"] != "pausada"],
                    key=lambda r: -r["score"])
    paused = sorted([r for r in rows if r["status"] == "pausada"],
                    key=lambda r: -r["score"])
    ordered = pinned + active + paused
    for i, row in enumerate(ordered, 1):
        row["rank"] = i
    return ordered


def signals_label(signals: dict) -> str:
    parts = []
    names = {"tasks": "tareas", "events": "eventos 7d", "decisions": "decis. 14d",
             "questions": "preguntas", "mail": "correo P1-P2"}
    for key, label in names.items():
        if signals.get(key):
            parts.append(f"{signals[key]} {label}")
    return " · ".join(parts) or "sin actividad"
