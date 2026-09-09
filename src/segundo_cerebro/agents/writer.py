"""Writing agent: borradores de informes y documentos desde la memoria.

Autonomía nivel 2, sin excepciones: SIEMPRE produce un borrador para
revisión humana, guardado solo en .brain/drafts/ — este agente no envía
ni publica nada.

Dos modos:
- Claude: redacta el borrador usando ÚNICAMENTE el material de la memoria
  (con fuentes citadas) y marca [FALTA: …] donde no hay datos. Viajan a la
  API los extractos relevantes de tu memoria (KOs y fragmentos de
  documentos del área/tema).
- Local (--no-llm o sin credenciales): entrega la plantilla + el material
  ordenado por sección, listo para que tú completes. Nada sale del equipo.

Línea roja clínica: ningún dato identificable de pacientes entra a la
memoria ni a los borradores; los documentos clínicos se generan como
estructura + evidencia y el dato del paciente se completa en el entorno
institucional.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from .. import extract as _extract

TEMPLATES_DIR = Path(os.environ.get("SB_TEMPLATES", "brain/templates/drafts"))
MATERIAL_MARK = "{{MATERIAL}}"
TOPIC_MARK = "{{TOPIC}}"


def list_templates(templates_dir: Path | None = None) -> list[str]:
    d = templates_dir or TEMPLATES_DIR
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.md"))


def load_template(kind: str, templates_dir: Path | None = None) -> str | None:
    path = (templates_dir or TEMPLATES_DIR) / f"{kind}.md"
    return path.read_text(encoding="utf-8") if path.exists() else None


# ── material desde la memoria ─────────────────────────────────────────────

def gather_material(store, topic: str, area: str | None = None,
                    limit: int = 12) -> dict:
    """Reúne lo que la memoria sabe del tema: decisiones, compromisos,
    eventos, preguntas, papers y extractos de documentos. Todo con fuente."""

    prefixes = [t.lower()[:6] for t in topic.split() if len(t) > 3]

    def _prefix_hits(ko_type):
        # tolera variaciones morfológicas que el FTS exacto pierde
        out = []
        for k in store.list_knowledge_objects(ko_type=ko_type, limit=500):
            hay = f"{k.title} {k.statement} {k.project or ''}".lower()
            if any(pref in hay for pref in prefixes):
                out.append(k)
        return out

    def _kos(ko_type):
        hits = [k for k in store.search_knowledge_objects(topic, limit=30)
                if k.ko_type == ko_type] or _prefix_hits(ko_type)
        if area:
            hits = [k for k in hits if k.area == area] or \
                   store.list_knowledge_objects(ko_type=ko_type, area=area, limit=limit)
        return hits[:limit]

    docs = store.search_documents(topic, limit=6)
    if not docs and prefixes:
        docs = [d for d in store.list_documents(limit=500)
                if any(pref in f"{d.title} {d.body[:2000]}".lower()
                       for pref in prefixes)][:6]
    if area and not docs:
        docs = [d for d in store.list_documents(limit=500) if d.area == area][:6]

    return {
        "topic": topic,
        "area": area,
        "decisions": [_slim_ko(k) for k in _kos("decision")],
        "tasks": [_slim_ko(k) for k in _kos("task")],
        "events": [_slim_ko(k) for k in _kos("event")],
        "questions": [_slim_ko(k) for k in _kos("question")],
        "papers": [
            {"title": d.title, "date": d.date, "path": d.path,
             "doi": d.metadata.get("doi"), "excerpt": d.body[:400]}
            for d in docs if d.doc_type == "paper"
        ],
        "documents": [
            {"title": d.title, "date": d.date, "path": d.path,
             "type": d.doc_type, "excerpt": d.body[:600]}
            for d in docs if d.doc_type != "paper"
        ],
    }


def _slim_ko(ko) -> dict:
    return {"statement": ko.statement, "date": ko.date, "people": ko.people,
            "status": ko.status, "source": ko.source_doc}


def material_markdown(material: dict) -> str:
    lines = ["## Material desde tu memoria", ""]
    sections = [("Decisiones", "decisions"), ("Compromisos", "tasks"),
                ("Eventos", "events"), ("Preguntas abiertas", "questions")]
    for title, key in sections:
        items = material.get(key, [])
        if items:
            lines.append(f"### {title}")
            for k in items:
                who = f" · {', '.join(k['people'])}" if k.get("people") else ""
                lines.append(f"- {k['date']} · {k['statement']}{who} "
                             f"(fuente: {k.get('source') or '—'})")
            lines.append("")
    for title, key, ref in (("Literatura", "papers", "doi"),
                            ("Documentos", "documents", "path")):
        items = material.get(key, [])
        if items:
            lines.append(f"### {title}")
            for d in items:
                lines.append(f"- {d['date']} · **{d['title']}** ({d.get(ref) or d['path']})")
            lines.append("")
    if len(lines) == 2:
        lines.append("_(la memoria aún no tiene material sobre este tema)_")
    return "\n".join(lines)


# ── generación ────────────────────────────────────────────────────────────

def scaffold(template: str, topic: str, material: dict) -> str:
    """Modo 100% local: plantilla + material listado, para completar a mano."""
    out = template.replace(TOPIC_MARK, topic)
    return out.replace(MATERIAL_MARK, material_markdown(material))


CLAUDE_PROMPT = """Eres el Writing agent de un segundo cerebro personal
(salud digital, investigación y gestión — Chile). Recibes una plantilla y
el material disponible en la memoria del usuario.

Redacta el BORRADOR completo siguiendo la estructura de la plantilla, con
estas reglas no negociables:
1. Usa ÚNICAMENTE el material entregado; no inventes datos, cifras ni citas.
2. Donde falte información escribe [FALTA: qué se necesita].
3. Cita la fuente de cada afirmación relevante: (fuente: …).
4. Registro profesional, prosa clara, español salvo que la plantilla sugiera inglés.
5. Es un borrador para revisión humana: no incluyas datos de pacientes
   jamás; si el material los tuviera, reemplázalos por [DATO CLÍNICO — completar
   en el sistema institucional].
Devuelve SOLO el markdown del borrador."""


def claude_draft(template: str, topic: str, material: dict) -> str:
    import anthropic

    client = anthropic.Anthropic()
    with client.messages.stream(
        model=os.environ.get("SB_MODEL", "claude-opus-5"),
        max_tokens=32000,
        system=[{"type": "text", "text": CLAUDE_PROMPT,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": (
            f"PLANTILLA:\n{template.replace(MATERIAL_MARK, '').replace(TOPIC_MARK, topic)}\n\n"
            f"MATERIAL DE LA MEMORIA (JSON):\n{json.dumps(material, ensure_ascii=False)}"
        )}],
    ) as stream:
        response = stream.get_final_message()
    return "".join(b.text for b in response.content if b.type == "text")


def draft(store, kind: str, topic: str, area: str | None = None,
          prefer_llm: bool = True, templates_dir: Path | None = None) -> tuple[str, str]:
    """Genera el borrador. Devuelve (markdown, modo)."""
    template = load_template(kind, templates_dir)
    if template is None:
        available = ", ".join(list_templates(templates_dir)) or "(ninguna)"
        raise FileNotFoundError(
            f"No existe la plantilla «{kind}». Disponibles: {available}")
    material = gather_material(store, topic, area=area)
    if prefer_llm:
        try:
            import anthropic  # noqa: F401
            return claude_draft(template, topic, material), "claude"
        except Exception:
            pass  # sin credenciales o error → andamiaje local
    return scaffold(template, topic, material), "local"


def save_draft(brain_dir: str | Path, kind: str, markdown: str) -> Path:
    drafts = Path(brain_dir) / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    n = 1
    while (path := drafts / f"{kind}-{stamp}-{n:02d}.md").exists():
        n += 1
    path.write_text(markdown, encoding="utf-8")
    return path
