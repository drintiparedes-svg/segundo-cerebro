"""`sb today` — el brief del día, construido 100% desde la memoria local.

Cruza: agenda (eventos sincronizados de Calendar), compromisos abiertos,
prioridades del último triaje de correo y preguntas sin resolver, agrupado
por área. No hace ninguna llamada externa.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .areas import Area

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def build_today(store, brain_dir: str | Path, areas: list[Area],
                horizon_days: int = 3) -> str:
    today = date.today()
    horizon = today + timedelta(days=horizon_days)
    area_names = {a.id: a.name for a in areas}
    name_of = lambda aid: area_names.get(aid, "Sin área")

    fecha = (f"{DIAS[today.weekday()]} {today.day} de "
             f"{MESES[today.month - 1]} de {today.year}")
    lines = [f"# Tu día — {fecha}", ""]

    # ── agenda ────────────────────────────────────────────────────────────
    events = [e for e in store.list_knowledge_objects(ko_type="event", limit=500)
              if str(today) <= e.date <= str(horizon)]
    events.sort(key=lambda e: e.date)
    lines.append("## Agenda")
    if events:
        for ev in events:
            who = f" · con {', '.join(ev.people)}" if ev.people else ""
            marker = "HOY → " if ev.date == str(today) else f"{ev.date} · "
            lines.append(f"- {marker}**{ev.title}**{who} [{name_of(ev.area)}]")
    else:
        lines.append("- Sin eventos en la memoria para los próximos "
                     f"{horizon_days} días. Conecta tu calendario: "
                     "`sb google connect <alias>` + `sb google sync`.")
    lines.append("")

    # ── preparación de reuniones de hoy ──────────────────────────────────
    for ev in [e for e in events if e.date == str(today) and e.people]:
        lines.append(f"### Prep · {ev.title}")
        for person in ev.people:
            open_items = store.list_knowledge_objects(person=person, status="active", limit=5)
            for item in open_items:
                if item.ko_type in ("task", "question", "decision"):
                    lines.append(f"- [{item.ko_type}] {item.statement} "
                                 f"(fuente: {item.source_doc or '—'})")
        lines.append("")

    # ── compromisos abiertos por área ─────────────────────────────────────
    lines.append("## Compromisos abiertos")
    tasks = store.list_knowledge_objects(ko_type="task", status="active", limit=200)
    if tasks:
        by_area: dict = {}
        for t in tasks:
            by_area.setdefault(t.area, []).append(t)
        for aid, items in sorted(by_area.items(), key=lambda kv: name_of(kv[0])):
            lines.append(f"### {name_of(aid)}")
            for t in sorted(items, key=lambda x: x.date, reverse=True)[:8]:
                lines.append(f"- {t.statement} ({t.date})")
    else:
        lines.append("- Nada pendiente registrado.")
    lines.append("")

    # ── correo prioritario (último triaje local) ─────────────────────────
    triage_path = Path(brain_dir) / "reports" / "latest-triage.json"
    if triage_path.exists():
        mail = json.loads(triage_path.read_text(encoding="utf-8"))
        urgent = [m for m in mail if m.get("priority", 5) <= 2]
        lines.append("## Correo que espera algo de ti")
        if urgent:
            for m in urgent[:8]:
                lines.append(f"- P{m['priority']} · **{m.get('subject', '')}** "
                             f"— {m.get('from', '')}")
        else:
            lines.append("- Nada urgente en el último triaje.")
        lines.append("")

    # ── preguntas sin resolver ───────────────────────────────────────────
    questions = store.list_knowledge_objects(ko_type="question", status="active", limit=10)
    if questions:
        lines.append("## Sin resolver")
        for q in questions:
            lines.append(f"- {q.statement} [{name_of(q.area)}]")
        lines.append("")

    lines.append("---")
    lines.append("_Generado localmente desde tu memoria; ninguna llamada externa._")
    return "\n".join(lines)
