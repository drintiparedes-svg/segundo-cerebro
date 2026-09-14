"""Agentes de flujo: proponen acciones concretas a partir de tu memoria.

Ninguno actúa por su cuenta: cada uno entrega ítems a la bandeja
(`queue.submit`), y la matriz de autonomía decide si se ejecuta con
registro y deshacer, si espera tu aprobación o si queda como sugerencia.
Corren en el paso `flows` de `sb refresh` o con `sb flows`.

- meeting_prep:     24 h antes de cada reunión, dossier de asistentes y pendientes.
- focus_block:      compromiso que vence en ≤2 días → bloque de foco en tu calendario.
- mail_reply_draft: correo P1 de una persona fijada → borrador de respuesta (no se envía).
- weekly_review:    los lunes, revisión semanal guardada.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from .. import queue
from ..people import pinned_names

FOCUS_START_HOUR = 9
MIN_FOCUS_HOURS = 1.0


def _calendar_account(brain_dir: Path) -> str | None:
    from ..connectors.registry import load_instances
    for inst in load_instances(brain_dir)["instances"]:
        if inst["type"] == "gcalendar" and inst.get("enabled", True):
            return inst["config"].get("account")
    return None


def _gmail_account(brain_dir: Path, preferred: str | None) -> str | None:
    from ..connectors.registry import load_instances
    accounts = [i["config"].get("account") for i in load_instances(brain_dir)["instances"]
                if i["type"] == "gmail" and i.get("enabled", True)]
    if preferred in accounts:
        return preferred
    return accounts[0] if accounts else None


def build_meeting_prep(store, event) -> str:
    """Dossier Markdown: por cada asistente, pendientes con esa persona;
    documentos relacionados por título; agenda propuesta."""
    lines = [f"# Preparación · {event.title}", f"Fecha: {event.date}", ""]
    if event.people:
        lines.append(f"Asistentes: {', '.join(event.people)}")
        lines.append("")
    agenda = []
    for person in event.people[:6]:
        items = store.list_knowledge_objects(person=person, status="active", limit=8)
        rel = [k for k in items if k.ko_type in ("task", "question", "decision") and k.id != event.id]
        if rel:
            lines.append(f"## {person}")
            for k in rel:
                lines.append(f"- [{k.ko_type}] {k.statement} (fuente: {k.source_doc or '—'})")
                if k.ko_type in ("task", "question"):
                    agenda.append(f"{k.title} ({person})")
            lines.append("")
    docs = store.search_documents(event.title, limit=5)
    if docs:
        lines.append("## Documentos relacionados")
        lines += [f"- {d.title} ({d.date}) — {d.path}" for d in docs]
        lines.append("")
    lines.append("## Agenda propuesta")
    lines += [f"{i}. {a}" for i, a in enumerate(agenda[:6], 1)] or ["1. Objetivo de la reunión", "2. Acuerdos y próximos pasos"]
    lines += ["", "_Borrador generado localmente desde tu memoria; revisa antes de usar._"]
    return "\n".join(lines)


def reply_template(store, mail: dict, brain_dir: Path) -> str:
    """Borrador de respuesta local (sin Claude): reconoce el asunto y lista
    lo pendiente con esa persona desde la memoria."""
    from ..agents.mail_triage import sender_name
    name = sender_name(mail.get("from", ""))
    first = name.split()[0] if name else ""
    items = store.list_knowledge_objects(person=first, status="active", limit=5) if first else []
    lines = [f"Hola {first},", "", f"Gracias por tu correo sobre «{mail.get('subject', '')}»."]
    pend = [k for k in items if k.ko_type in ("task", "question")]
    if pend:
        lines.append("Te comparto dónde estamos con lo pendiente entre nosotros:")
        lines += [f"- {k.statement}" for k in pend[:4]]
    lines += ["", "Quedo atento a tus comentarios.", "", "Saludos,", "Inti",
              "", "[Borrador preparado por tu segundo cerebro — revisa y completa antes de enviar]"]
    return "\n".join(lines)


def run_flows(store, brain_dir: str | Path, today: date | None = None) -> dict:
    brain_dir = Path(brain_dir)
    today = today or date.today()
    tomorrow = str(today + timedelta(days=1))
    soon = str(today + timedelta(days=2))
    out = {"created": [], "executed": [], "queued": [], "suggested": [], "duplicates": 0, "manual": []}

    def track(item):
        if item.get("duplicate"):
            out["duplicates"] += 1
            return
        out["created"].append(item["id"])
        bucket = {"executed": "executed", "pending": "queued", "suggested": "suggested",
                  "manual": "manual", "failed": "manual"}.get(item["status"])
        if bucket:
            out[bucket].append({"id": item["id"], "title": item["title"], "status": item["status"]})

    # ── preparación de reuniones (mañana) ─────────────────────────────────
    for ev in store.list_knowledge_objects(ko_type="event", limit=2000):
        if ev.date != tomorrow or not ev.people:
            continue
        key = f"meeting_prep:{ev.id}"
        if queue.exists(brain_dir, key):
            out["duplicates"] += 1
            continue
        md = build_meeting_prep(store, ev)
        track(queue.submit(brain_dir, store, "meeting_prep", "draft_note",
                           f"Preparar «{ev.title}» ({ev.date})",
                           {"kind": "prep", "markdown": md},
                           rationale=f"reunión mañana con {', '.join(ev.people[:4])}",
                           key=key, source_doc=ev.source_doc))

    # ── bloques de foco para lo que vence ─────────────────────────────────
    account = _calendar_account(brain_dir)
    from ..workload import estimate_effort, history_medians
    medians = history_medians(store)
    for ko in store.list_knowledge_objects(ko_type="task", status="active", limit=5000):
        if not ko.valid_to or not (str(today) <= ko.valid_to <= soon):
            continue
        effort, _ = estimate_effort(ko, medians)
        if effort < MIN_FOCUS_HOURS:
            continue
        key = f"focus_block:{ko.id}"
        if queue.exists(brain_dir, key):
            out["duplicates"] += 1
            continue
        day = ko.scheduled_for if ko.scheduled_for and ko.scheduled_for >= str(today) else str(today)
        start = datetime.fromisoformat(f"{day}T{FOCUS_START_HOUR:02d}:00:00")
        end = start + timedelta(hours=min(effort, 4.0))
        payload = {"account": account, "summary": f"Foco · {ko.title}",
                   "start": start.isoformat(), "end": end.isoformat(),
                   "description": f"Compromiso que vence {ko.valid_to}: {ko.statement}"}
        track(queue.submit(brain_dir, store, "focus_block", "calendar_block",
                           f"Bloque de foco: {ko.title} ({day}, {min(effort, 4.0)} h)", payload,
                           rationale=f"vence {ko.valid_to}; esfuerzo {effort} h",
                           key=key, source_doc=ko.source_doc,
                           decision=None if account else "queue"))

    # ── borradores de respuesta a P1 de personas fijadas ──────────────────
    triage_path = brain_dir / "reports" / "latest-triage.json"
    if triage_path.exists():
        pinned = [p.lower() for p in pinned_names(brain_dir)]
        for mail in json.loads(triage_path.read_text(encoding="utf-8")):
            if mail.get("priority", 5) != 1 or not mail.get("id"):
                continue
            sender = (mail.get("from") or "").lower()
            if not any(p in sender for p in pinned):
                continue
            key = f"mail_reply:{mail['id']}"
            if queue.exists(brain_dir, key):
                out["duplicates"] += 1
                continue
            acc = _gmail_account(brain_dir, mail.get("account"))
            payload = {"account": acc, "to": mail.get("from", ""),
                       "subject": "Re: " + (mail.get("subject") or ""),
                       "body": reply_template(store, mail, brain_dir)}
            track(queue.submit(brain_dir, store, "mail_reply_draft", "gmail_draft",
                               f"Borrador de respuesta a {mail.get('from', '')[:40]}: {mail.get('subject', '')[:50]}",
                               payload, rationale="correo P1 de una persona fijada",
                               key=key, decision=None if acc else "queue"))

    # ── revisión semanal (lunes) ──────────────────────────────────────────
    if today.weekday() == 0:
        key = f"weekly_review:{today.isoformat()}"
        if not queue.exists(brain_dir, key):
            track(queue.submit(brain_dir, store, "weekly_review", "weekly_review",
                               f"Revisión semanal {today.isoformat()}", {}, key=key,
                               rationale="lunes: cierre de la semana anterior"))
        else:
            out["duplicates"] += 1
    return out
