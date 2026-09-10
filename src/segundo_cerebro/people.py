"""Personas clave: ranking automático + pin manual.

Un pin no es un dato del grafo: es tu validación, y vive en
.brain/people_overrides.json (mismo patrón que las áreas). El ranking se
calcula localmente desde el grafo, la actividad reciente, las reuniones
próximas y el último triaje de correo (solo metadatos).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

WEIGHTS = {"degree": 2, "recent": 3, "upcoming": 5, "mail": 4}
SUGGEST_MIN_SCORE = 8
SUGGEST_MAX = 5


def _overrides_path(brain_dir: str | Path) -> Path:
    return Path(brain_dir) / "people_overrides.json"


def load_people_overrides(brain_dir: str | Path) -> dict:
    path = _overrides_path(brain_dir)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def set_person_override(brain_dir: str | Path, name: str, pin: bool | None = None,
                        role: str | None = None, area: str | None = None,
                        note: str | None = None) -> dict:
    overrides = load_people_overrides(brain_dir)
    entry = overrides.setdefault(name, {})
    if pin is not None:
        entry["pin"] = bool(pin)
    if role is not None:
        entry["role"] = role
    if area is not None:
        entry["area"] = area
    if note is not None:
        entry["note"] = note
    if not entry.get("pin") and not any(entry.get(k) for k in ("role", "area", "note")):
        overrides.pop(name, None)
    path = _overrides_path(brain_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return entry


def pinned_names(brain_dir: str | Path) -> list[str]:
    return [n for n, e in load_people_overrides(brain_dir).items() if e.get("pin")]


def _latest_triage(brain_dir: str | Path) -> list[dict]:
    path = Path(brain_dir) / "reports" / "latest-triage.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def _sender_name(from_header: str) -> str:
    head = from_header.split("<")[0].strip().strip('"')
    return head or from_header.split("@")[0]


def people_scores(store, brain_dir: str | Path, today: date | None = None) -> dict:
    """{"people": [ranking], "suggested": [nombres], "unknown_senders": [...]}"""
    today = today or date.today()
    since = str(today - timedelta(days=30))
    overrides = load_people_overrides(brain_dir)
    triage = _latest_triage(brain_dir)

    mail_hits: dict[str, int] = {}
    for m in triage:
        if m.get("priority", 5) <= 2:
            name = _sender_name(m.get("from", "")).lower()
            mail_hits[name] = mail_hits.get(name, 0) + 1

    kos = store.list_knowledge_objects(limit=2000)
    rows = []
    for ent in store.list_entities(entity_type="person"):
        low = ent.name.lower()
        degree = len(store.relationships_of(ent.id))
        recent = sum(1 for k in kos if k.date >= since and ent.name in k.people)
        upcoming = sum(1 for k in kos if k.ko_type == "event" and k.date >= str(today)
                       and ent.name in k.people)
        mail = sum(c for sender, c in mail_hits.items() if low in sender or sender in low)
        score = (degree * WEIGHTS["degree"] + recent * WEIGHTS["recent"]
                 + upcoming * WEIGHTS["upcoming"] + mail * WEIGHTS["mail"])
        ov = overrides.get(ent.name, {})
        rows.append({"id": ent.id, "name": ent.name, "score": score,
                     "signals": {"degree": degree, "recent": recent,
                                 "upcoming": upcoming, "mail": mail},
                     "pinned": bool(ov.get("pin")), "role": ov.get("role"),
                     "area": ov.get("area"), "note": ov.get("note")})
    rows.sort(key=lambda r: (not r["pinned"], -r["score"], r["name"].lower()))
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    suggested = [r["name"] for r in rows
                 if not r["pinned"] and r["score"] >= SUGGEST_MIN_SCORE][:SUGGEST_MAX]

    # remitentes frecuentes que no están en el grafo (solo nombre)
    known = {r["name"].lower() for r in rows}
    counts: dict[str, int] = {}
    for m in triage:
        if m.get("priority", 5) <= 3:
            name = _sender_name(m.get("from", ""))
            if name and not any(name.lower() in k or k in name.lower() for k in known):
                counts[name] = counts.get(name, 0) + 1
    unknown = [{"name": n, "mails": c} for n, c in
               sorted(counts.items(), key=lambda kv: -kv[1]) if c >= 2][:SUGGEST_MAX]

    return {"people": rows, "suggested": suggested, "unknown_senders": unknown}


def signals_label(signals: dict) -> str:
    parts = []
    if signals.get("upcoming"):
        parts.append(f"{signals['upcoming']} reunión(es) próximas")
    if signals.get("recent"):
        parts.append(f"{signals['recent']} menciones 30d")
    if signals.get("mail"):
        parts.append(f"{signals['mail']} correos P1-P2")
    if signals.get("degree"):
        parts.append(f"{signals['degree']} relaciones")
    return " · ".join(parts) or "sin señales"


def key_people_brief(store, brain_dir: str | Path, today: date | None = None,
                     horizon_days: int = 14) -> list[str]:
    """Líneas Markdown de la sección «Personas clave» del brief."""
    today = today or date.today()
    horizon = str(today + timedelta(days=horizon_days))
    lines = []
    for name in pinned_names(brain_dir):
        items = store.list_knowledge_objects(person=name, status="active", limit=200)
        nxt = sorted((k for k in items if k.ko_type == "event"
                      and str(today) <= k.date <= horizon), key=lambda k: k.date)
        tasks = [k for k in items if k.ko_type == "task"]
        questions = [k for k in items if k.ko_type == "question"]
        ov = load_people_overrides(brain_dir).get(name, {})
        role = f" — {ov['role']}" if ov.get("role") else ""
        lines.append(f"### 📌 {name}{role}")
        if nxt:
            lines.append(f"- Próxima reunión: {nxt[0].date} · {nxt[0].title}")
        for t in tasks[:4]:
            lines.append(f"- [task] {t.statement}")
        for q in questions[:2]:
            lines.append(f"- [question] {q.statement}")
        if not (nxt or tasks or questions):
            lines.append("- Sin pendientes registrados con esta persona.")
        lines.append("")
    return lines
