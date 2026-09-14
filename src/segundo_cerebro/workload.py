"""Cockpit de carga: cuánto cabe hoy y en los próximos 7 días.

Capacidad diaria (jornada configurable) menos horas de agenda (eventos
sincronizados de Calendar), contra el esfuerzo de los compromisos abiertos.
El esfuerzo se infiere (duración del plan Excel, tipo de tarea, mediana
histórica por proyecto) y se ajusta con un clic. La planificación es
greedy y explicable: atrasadas → vencen antes → área mejor rankeada, en
los huecos libres de cada día. 100% local, sin llamadas externas.
"""

from __future__ import annotations

import re
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path

from .models import KnowledgeObject

DEFAULT_WORKDAY = {"start": "08:30", "end": "18:00", "days": [1, 2, 3, 4, 5],
                   "focus_ratio": 0.6, "meeting_default_min": 60}
DEFAULT_EFFORT = {"task": 1.0, "question": 0.5, "decision": 0.5, "opportunity": 2.0}
FOCUS_HOURS_PER_PLAN_DAY = 4.0
DURATION_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(d[ií]as?|h(?:oras?)?|min(?:utos?)?|sem(?:anas?)?)", re.IGNORECASE)
DIAS_CORTO = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def _hours(text: str) -> float:
    h, m = text.split(":")
    return int(h) + int(m) / 60


def capacity_hours(cfg: dict, day: date) -> float:
    wd = {**DEFAULT_WORKDAY, **(cfg.get("workday") or {})}
    if (day.weekday() + 1) not in wd["days"]:
        return 0.0
    return max(0.0, _hours(wd["end"]) - _hours(wd["start"]))


def parse_duration_hours(text: str | None) -> float | None:
    """«5 días» → 20 h de foco · «3 h» → 3 · «90 min» → 1.5 · «2 semanas» → 40."""
    if not text:
        return None
    m = DURATION_RE.search(text)
    if not m:
        return None
    n = float(m.group(1).replace(",", "."))
    unit = m.group(2).lower()
    if unit.startswith("d"):
        return n * FOCUS_HOURS_PER_PLAN_DAY
    if unit.startswith("sem"):
        return n * 5 * FOCUS_HOURS_PER_PLAN_DAY
    if unit.startswith("min"):
        return round(n / 60, 2)
    return n


def history_medians(store) -> dict[str, float]:
    """Mediana de esfuerzo de tareas cerradas con esfuerzo registrado, por proyecto."""
    by_project: dict[str, list[float]] = {}
    for ko in store.list_knowledge_objects(ko_type="task", status="done", limit=5000):
        if ko.effort_h and ko.project:
            by_project.setdefault(ko.project, []).append(float(ko.effort_h))
    return {p: statistics.median(v) for p, v in by_project.items()}


def estimate_effort(ko: KnowledgeObject, medians: dict[str, float] | None = None) -> tuple[float, str]:
    """(horas, origen). El valor guardado manda; luego la duración del plan,
    la mediana histórica del proyecto y, al final, el tipo de tarea."""
    if ko.effort_h:
        return float(ko.effort_h), "ajustado"
    for tag in ko.tags or []:
        if tag.lower().startswith("duracion:"):
            h = parse_duration_hours(tag.split(":", 1)[1])
            if h:
                return h, "plan"
    if medians and ko.project in medians:
        return medians[ko.project], "histórico"
    return DEFAULT_EFFORT.get(ko.ko_type, 1.0), "tipo"


def meetings_by_day(store, first: date, days: int, cfg: dict) -> dict[str, float]:
    """Horas de agenda por día desde los eventos de Calendar (duración real
    si viene en metadatos; si no, el valor por defecto). Los eventos de día
    completo no restan capacidad."""
    wd = {**DEFAULT_WORKDAY, **(cfg.get("workday") or {})}
    default_h = wd["meeting_default_min"] / 60
    last = first + timedelta(days=days - 1)
    hours: dict[str, float] = {}
    seen_days_with_docs: set[str] = set()
    for doc in store.list_documents(limit=100_000):
        if (doc.metadata or {}).get("source") != "google-calendar":
            continue
        if not (str(first) <= doc.date <= str(last)):
            continue
        meta = doc.metadata
        if meta.get("all_day"):
            seen_days_with_docs.add(doc.date)
            continue
        minutes = meta.get("duration_min")
        hours[doc.date] = hours.get(doc.date, 0.0) + (float(minutes) / 60 if minutes else default_h)
        seen_days_with_docs.add(doc.date)
    # eventos que solo existen como KO (notas a mano): se cuentan si ese día
    # no tiene agenda sincronizada
    for ev in store.list_knowledge_objects(ko_type="event", limit=5000):
        if str(first) <= ev.date <= str(last) and ev.date not in seen_days_with_docs:
            hours[ev.date] = hours.get(ev.date, 0.0) + (float(ev.effort_h) if ev.effort_h else default_h)
    return hours


def _sort_key(ko: KnowledgeObject, today: date, area_rank: dict):
    overdue = bool(ko.valid_to and ko.valid_to < str(today))
    return (0 if overdue else 1, ko.valid_to or "9999-12-31",
            area_rank.get(ko.area, 999), ko.date)


def plan_week(store, cfg: dict, today: date | None = None, days: int = 7,
              area_rank: dict | None = None, persist: bool = True) -> dict:
    today = today or date.today()
    area_rank = area_rank or {}
    wd = {**DEFAULT_WORKDAY, **(cfg.get("workday") or {})}
    meetings = meetings_by_day(store, today, days, cfg)
    medians = history_medians(store)

    slots = []
    for i in range(days):
        d = today + timedelta(days=i)
        cap = capacity_hours(cfg, d)
        meet = round(meetings.get(str(d), 0.0), 2)
        focus = max(0.0, (cap - meet) * wd["focus_ratio"])
        slots.append({"date": str(d), "weekday": DIAS_CORTO[d.weekday()], "capacity_h": cap,
                      "meetings_h": meet, "focus_h": round(focus, 2), "planned_h": 0.0,
                      "items": []})
    by_date = {s["date"]: s for s in slots}
    window_last = slots[-1]["date"]

    tasks = [t for t in store.list_knowledge_objects(ko_type="task", status="active", limit=5000)]
    tasks.sort(key=lambda k: _sort_key(k, today, area_rank))
    unscheduled, overloaded = [], set()

    def item(ko, effort, origin, overdue):
        return {"id": ko.id, "title": ko.title, "effort_h": effort, "effort_origin": origin,
                "valid_to": ko.valid_to, "area": ko.area, "project": ko.project,
                "overdue": overdue, "fixed": "fijado" in (ko.tags or [])}

    for ko in tasks:
        effort, origin = estimate_effort(ko, medians)
        effort = round(effort, 2)
        overdue = bool(ko.valid_to and ko.valid_to < str(today))
        fixed = "fijado" in (ko.tags or []) and ko.scheduled_for and ko.scheduled_for in by_date
        chosen = None
        if fixed:
            chosen = by_date[ko.scheduled_for]
        else:
            limit = ko.valid_to if ko.valid_to and str(today) <= ko.valid_to <= window_last else window_last
            candidates = [s for s in slots if s["date"] <= limit and s["capacity_h"] > 0]
            chosen = next((s for s in candidates if s["focus_h"] - s["planned_h"] >= effort), None)
            if chosen is None and candidates:
                # no cabe entero: va al día límite (o hoy si está atrasada) y marca sobrecarga
                chosen = candidates[0] if overdue else candidates[-1]
                overloaded.add(chosen["date"])
        if chosen is None:
            unscheduled.append(item(ko, effort, origin, overdue))
            continue
        chosen["planned_h"] = round(chosen["planned_h"] + effort, 2)
        chosen["items"].append(item(ko, effort, origin, overdue))
        if persist and ko.scheduled_for != chosen["date"]:
            store.update_ko(ko.id, scheduled_for=chosen["date"])

    for s in slots:
        s["free_h"] = round(max(0.0, s["focus_h"] - s["planned_h"]), 2)
        s["load_pct"] = (round(100 * (s["meetings_h"] + s["planned_h"]) / s["capacity_h"])
                         if s["capacity_h"] else 0)
        s["overloaded"] = s["date"] in overloaded or s["planned_h"] > s["focus_h"] + 1e-9
    totals = {"capacity_h": round(sum(s["capacity_h"] for s in slots), 1),
              "meetings_h": round(sum(s["meetings_h"] for s in slots), 1),
              "planned_h": round(sum(s["planned_h"] for s in slots), 1),
              "tasks": sum(len(s["items"]) for s in slots),
              "unscheduled": len(unscheduled),
              "overloaded_days": sorted(overloaded)}
    return {"today": str(today), "days": slots, "unscheduled": unscheduled, "totals": totals,
            "workday": wd}


def today_lines(plan: dict) -> list[str]:
    """Sección «Carga de hoy» para el brief."""
    d = plan["days"][0]
    lines = [f"## Carga de hoy — {d['meetings_h']} h de agenda + {d['planned_h']} h de tareas "
             f"/ {d['capacity_h']} h" + (" · ⚠ sobrecargado" if d["overloaded"] else "")]
    for it in d["items"][:8]:
        mark = "⚠ " if it["overdue"] else ""
        lines.append(f"- {mark}{it['title']} ({it['effort_h']} h{', vence ' + it['valid_to'] if it['valid_to'] else ''})")
    if not d["items"]:
        lines.append("- Sin tareas planificadas para hoy." if d["capacity_h"] else "- Día sin jornada.")
    lines.append("")
    return lines


def projection_lines(plan: dict) -> list[str]:
    """Sección «Proyección» para la revisión semanal."""
    lines = ["## Proyección de la semana"]
    for d in plan["days"]:
        if not d["capacity_h"]:
            continue
        bar = "█" * int(round(min(d["load_pct"], 150) / 10)) or "·"
        lines.append(f"- {d['weekday']} {d['date']}: {bar} {d['load_pct']}% "
                     f"(agenda {d['meetings_h']} h · tareas {d['planned_h']} h · libre {d['free_h']} h)"
                     + (" ⚠" if d["overloaded"] else ""))
    t = plan["totals"]
    if t["overloaded_days"]:
        lines.append(f"- Días sobrecargados: {', '.join(t['overloaded_days'])} — mover, delegar o recortar.")
    if plan["unscheduled"]:
        lines.append(f"- Sin espacio esta semana: {len(plan['unscheduled'])} tareas "
                     f"({', '.join(u['title'] for u in plan['unscheduled'][:4])}…)")
    lines.append("")
    return lines
