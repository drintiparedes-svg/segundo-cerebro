"""Capa de procesamiento cognitivo: documento → knowledge objects + grafo.

Dos extractores:
- HeuristicExtractor: reglas y convenciones de escritura (sin dependencias).
- ClaudeExtractor: extracción semántica con la API de Claude (opcional).

El pipeline usa Claude si hay credenciales disponibles y cae a heurísticas
si no las hay, de modo que el sistema siempre funciona.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import (
    Document, Entity, KnowledgeObject, Relationship, new_id,
)

DECISION_RE = re.compile(r"^\s*(?:DECISI[OÓ]N|DECISION)\s*:\s*(.+)$", re.IGNORECASE)
TASK_RE = re.compile(r"^\s*[-*]\s*\[ \]\s*(.+)$")
QUESTION_RE = re.compile(r"^\s*(?:PREGUNTA|PENDIENTE|OPEN)\s*:\s*(.+)$", re.IGNORECASE)
IDEA_RE = re.compile(r"^\s*IDEA\s*:\s*(.+)$", re.IGNORECASE)
HYPOTHESIS_RE = re.compile(r"^\s*(?:HIP[OÓ]TESIS|HYPOTHESIS)\s*:\s*(.+)$", re.IGNORECASE)


@dataclass
class ExtractionResult:
    knowledge_objects: list[KnowledgeObject] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)


class HeuristicExtractor:
    """Extracción basada en convenciones de escritura del vault.

    Convenciones (ver brain/templates/):
      - `DECISIÓN: ...`   → knowledge object tipo decision
      - `- [ ] ...`       → task / compromiso
      - `PREGUNTA: ...`   → question abierta
      - `IDEA: ...`       → idea
      - `HIPÓTESIS: ...`  → hypothesis
      - frontmatter `people`, `project`, `organizations` → entidades + relaciones
    """

    def extract(self, doc: Document) -> ExtractionResult:
        result = ExtractionResult()
        meta = doc.metadata

        people = _as_list(meta.get("people"))
        orgs = _as_list(meta.get("organizations"))
        project = meta.get("project")
        tags = _as_list(meta.get("tags"))

        person_entities = [
            Entity(id=new_id("ent"), name=p, entity_type="person") for p in people
        ]
        org_entities = [
            Entity(id=new_id("ent"), name=o, entity_type="organization") for o in orgs
        ]
        result.entities.extend(person_entities + org_entities)
        if project:
            result.entities.append(
                Entity(id=new_id("ent"), name=str(project), entity_type="project")
            )

        # Toda reunión es un evento episódico en la línea de tiempo.
        if doc.doc_type == "meeting":
            result.knowledge_objects.append(KnowledgeObject(
                id=new_id("ko"), ko_type="event", title=doc.title,
                statement=f"Reunión registrada: {doc.title}",
                date=doc.date, people=people, project=project,
                confidence="confirmed", source_doc=doc.id, tags=tags,
                valid_from=doc.date,
            ))

        for line in doc.body.splitlines():
            for regex, ko_type in (
                (DECISION_RE, "decision"), (TASK_RE, "task"),
                (QUESTION_RE, "question"), (IDEA_RE, "idea"),
                (HYPOTHESIS_RE, "hypothesis"),
            ):
                m = regex.match(line)
                if m:
                    text = m.group(1).strip()
                    result.knowledge_objects.append(KnowledgeObject(
                        id=new_id("ko"), ko_type=ko_type,
                        title=text[:80], statement=text,
                        date=doc.date, people=people, project=project,
                        confidence="confirmed" if ko_type == "decision" else "probable",
                        source_doc=doc.id, tags=tags, valid_from=doc.date,
                    ))
                    break

        return result


class ClaudeExtractor:
    """Extracción semántica con Claude. Requiere el paquete `anthropic`
    y credenciales (ANTHROPIC_API_KEY o perfil de `ant auth login`)."""

    PROMPT = """Eres la capa de procesamiento cognitivo de un segundo cerebro personal.
Analiza el documento y devuelve SOLO un JSON válido con esta forma:

{
  "knowledge_objects": [
    {"ko_type": "decision|task|fact|idea|question|hypothesis|event",
     "title": "...", "statement": "...", "people": ["..."],
     "project": "... o null", "confidence": "confirmed|probable|tentative",
     "tags": ["..."]}
  ],
  "entities": [
    {"name": "...", "entity_type": "person|organization|project|concept"}
  ],
  "relationships": [
    {"source": "nombre entidad", "target": "nombre entidad",
     "rel_type": "works_with|leads|develops|sponsors|studies|collaborates"}
  ]
}

Reglas: extrae decisiones con su rationale, compromisos con responsable,
preguntas abiertas, hechos relevantes y las relaciones entre personas,
organizaciones y proyectos. No inventes nada que no esté en el texto."""

    def __init__(self, model: str | None = None):
        import os
        self.model = model or os.environ.get("SB_MODEL", "claude-opus-5")

    def extract(self, doc: Document) -> ExtractionResult:
        import json
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=self.model,
            max_tokens=16000,
            system=[{
                "type": "text",
                "text": self.PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": f"Título: {doc.title}\nFecha: {doc.date}\n"
                           f"Tipo: {doc.doc_type}\n\n{doc.body}",
            }],
        )
        text = next(b.text for b in response.content if b.type == "text")
        payload = json.loads(_strip_fences(text))

        result = ExtractionResult()
        for ko in payload.get("knowledge_objects", []):
            result.knowledge_objects.append(KnowledgeObject(
                id=new_id("ko"),
                ko_type=ko.get("ko_type", "fact"),
                title=ko.get("title", "")[:120],
                statement=ko.get("statement", ""),
                date=doc.date,
                people=_as_list(ko.get("people")),
                project=ko.get("project") or doc.metadata.get("project"),
                confidence=ko.get("confidence", "probable"),
                source_doc=doc.id,
                tags=_as_list(ko.get("tags")),
                valid_from=doc.date,
            ))
        for ent in payload.get("entities", []):
            result.entities.append(Entity(
                id=new_id("ent"), name=ent["name"],
                entity_type=ent.get("entity_type", "concept"),
            ))
        name_index = {e.name: e for e in result.entities}
        for rel in payload.get("relationships", []):
            src = name_index.get(rel.get("source"))
            tgt = name_index.get(rel.get("target"))
            if src and tgt:
                result.relationships.append(Relationship(
                    id=new_id("rel"), source_id=src.id, target_id=tgt.id,
                    rel_type=rel.get("rel_type", "related_to"),
                    valid_from=doc.date, source_doc=doc.id,
                ))
        return result


def get_extractor(prefer_llm: bool = True):
    """Devuelve el mejor extractor disponible."""
    if prefer_llm:
        try:
            import anthropic  # noqa: F401
            return ClaudeExtractor()
        except ImportError:
            pass
    return HeuristicExtractor()


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return [str(v) for v in value]


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()
