"""Agente de triaje de correo: prioriza la bandeja SIN modificarla.

Privacidad por diseño:
- Lee con scope gmail.readonly; no puede enviar, borrar ni marcar.
- Los correos no se guardan en la memoria del cerebro. El informe queda
  solo en .brain/reports/ (local, fuera de git).
- Modo local (--no-llm): la priorización se calcula en tu máquina y
  ningún dato del correo sale de ella.
- Modo Claude: por defecto viajan solo remitente, asunto, fecha y
  snippet; el cuerpo completo requiere include_bodies=True explícito.

Rasgo diferenciador: cruza cada remitente con el knowledge graph — un
correo de alguien con quien compartes proyectos pesa más que cualquier
newsletter.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

from ..connectors.gmail import sender_name
from .. import extract as _extract

PRIORITIES = {
    1: "P1 · Urgente",
    2: "P2 · Importante",
    3: "P3 · Responder cuando puedas",
    4: "P4 · Informativo",
    5: "P5 · Archivar",
}

URGENCY_WORDS = re.compile(
    r"\b(urgente|urgent|plazo|deadline|hoy|mañana|asap|vence|firma|"
    r"aprobaci[oó]n|recordatorio final|last call)\b", re.IGNORECASE)
ACTION_WORDS = re.compile(
    r"\b(puedes|podr[ií]as|necesito|favor|confirmar|revisar|enviar|"
    r"adjunto|responder|agendar|reuni[oó]n)\b", re.IGNORECASE)
NOISE_MARKERS = re.compile(
    r"(no-?reply|noreply|unsubscribe|newsletter|notificaci[oó]n|"
    r"promoci[oó]n|marketing)", re.IGNORECASE)
NOISE_LABELS = {"CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL", "CATEGORY_UPDATES"}


def _known_people(store) -> dict[str, int]:
    """nombre en minúsculas → nº de relaciones en el grafo."""
    people = {}
    for ent in store.list_entities(entity_type="person"):
        people[ent.name.lower()] = len(store.relationships_of(ent.id))
    return people


def heuristic_triage(emails: list[dict], store) -> list[dict]:
    """Puntuación 100% local, cruzada con el knowledge graph."""
    known = _known_people(store) if store else {}
    now = datetime.now(timezone.utc)
    triaged = []
    for mail in emails:
        score = 0
        reasons = []

        name = sender_name(mail.get("from", "")).lower()
        graph_hit = next((p for p in known if p in name or name in p), None)
        if graph_hit:
            rels = known[graph_hit]
            score += 40 + min(10, rels * 2)
            reasons.append(f"remitente en tu knowledge graph ({graph_hit}, "
                           f"{rels} relaciones)")

        text = f"{mail.get('subject', '')} {mail.get('snippet', '')}"
        if URGENCY_WORDS.search(text):
            score += 25
            reasons.append("lenguaje de urgencia/plazo")
        if ACTION_WORDS.search(text):
            score += 15
            reasons.append("pide una acción tuya")
        if mail.get("date"):
            try:
                sent = datetime.fromisoformat(mail["date"])
                if (now - sent.astimezone(timezone.utc)).total_seconds() < 86_400:
                    score += 10
                    reasons.append("recibido en las últimas 24 h")
            except ValueError:
                pass
        if NOISE_MARKERS.search(mail.get("from", "") + " " + text):
            score -= 30
            reasons.append("parece correo automático/newsletter")
        if NOISE_LABELS & set(mail.get("labels", [])):
            score -= 15
            reasons.append("categoría promociones/social/updates")

        if score >= 60:
            priority = 1
        elif score >= 40:
            priority = 2
        elif score >= 20:
            priority = 3
        elif score >= 0:
            priority = 4
        else:
            priority = 5
        triaged.append({**mail, "priority": priority, "score": score,
                        "reasons": reasons or ["sin señales fuertes"]})
    return sorted(triaged, key=lambda m: (m["priority"], -m["score"]))


CLAUDE_PROMPT = """Eres el agente de triaje de correo de un segundo cerebro
personal. Recibes correos (remitente, asunto, fecha, snippet y, si el
usuario lo autorizó, cuerpo) más la lista de personas del knowledge graph
del usuario con su número de relaciones. Prioriza cada correo:

1 = urgente (acción hoy) · 2 = importante · 3 = responder cuando pueda ·
4 = informativo · 5 = archivar/ruido

Pondera MÁS a remitentes presentes en el knowledge graph. Devuelve SOLO JSON:
{"triage": [{"id": "…", "priority": 1, "reason": "una frase",
             "suggested_action": "una frase"}]}
No inventes correos ni ids."""


def claude_triage(emails: list[dict], store) -> list[dict]:
    import anthropic

    known = _known_people(store) if store else {}
    payload = {
        "known_people": known,
        "emails": [
            {k: mail.get(k, "") for k in
             ("id", "from", "subject", "date", "snippet", "labels", "body")}
            for mail in emails
        ],
    }
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=os.environ.get("SB_MODEL", "claude-opus-5"),
        max_tokens=16000,
        system=[{"type": "text", "text": CLAUDE_PROMPT,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user",
                   "content": json.dumps(payload, ensure_ascii=False)}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    verdicts = {v["id"]: v for v in
                json.loads(_extract._strip_fences(text)).get("triage", [])}
    triaged = []
    for mail in emails:
        v = verdicts.get(mail["id"], {})
        triaged.append({
            **mail,
            "priority": int(v.get("priority", 4)),
            "score": 0,
            "reasons": [v.get("reason", "sin evaluación")],
            "suggested_action": v.get("suggested_action", ""),
        })
    return sorted(triaged, key=lambda m: m["priority"])


def triage(emails: list[dict], store, prefer_llm: bool = True) -> list[dict]:
    if prefer_llm:
        try:
            import anthropic  # noqa: F401
            return claude_triage(emails, store)
        except Exception:
            pass  # sin credenciales o error → modo 100% local
    return heuristic_triage(emails, store)


def to_markdown(triaged: list[dict]) -> str:
    lines = ["# Triaje de correo", "",
             f"{len(triaged)} correos evaluados. Solo lectura: tu bandeja "
             "no fue modificada.", ""]
    current = None
    for mail in triaged:
        if mail["priority"] != current:
            current = mail["priority"]
            lines += [f"## {PRIORITIES[current]}", ""]
        sender = sender_name(mail.get("from", "?"))
        lines.append(f"- **{mail.get('subject', '(sin asunto)')}** — {sender} "
                     f"({mail.get('account', '')})")
        lines.append(f"  - {'; '.join(mail.get('reasons', []))}")
        if mail.get("suggested_action"):
            lines.append(f"  - Acción sugerida: {mail['suggested_action']}")
    lines.append("")
    return "\n".join(lines)
