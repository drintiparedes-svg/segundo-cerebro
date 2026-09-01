"""Modelos de dominio del Segundo Cerebro.

La unidad fundamental no es la nota sino el Knowledge Object (KO): una pieza
atómica de conocimiento con tipo, personas, proyecto, temporalidad, confianza
y trazabilidad hacia su documento fuente.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

# Tipos de Knowledge Object soportados en V1.
KO_TYPES = (
    "decision",     # decisión tomada, con rationale
    "task",         # compromiso / tarea con posible responsable y fecha
    "fact",         # hecho declarativo (memoria semántica)
    "idea",         # idea o propuesta
    "question",     # pregunta abierta / no resuelto
    "hypothesis",   # hipótesis a validar
    "event",        # evento episódico (reunión, hito)
)

CONFIDENCE_LEVELS = ("confirmed", "probable", "tentative")
STATUSES = ("active", "done", "superseded", "archived")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass
class Document:
    """Documento fuente tal como entró al sistema (capa de captura)."""

    id: str
    path: str
    title: str
    doc_type: str          # meeting | note | paper | email | transcript | other
    date: str              # fecha del contenido (YYYY-MM-DD), no de ingesta
    body: str
    metadata: dict = field(default_factory=dict)
    ingested_at: str = field(default_factory=now_iso)

    @staticmethod
    def content_hash(body: str) -> str:
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass
class Entity:
    """Nodo del grafo: persona, organización, proyecto o concepto."""

    id: str
    name: str
    entity_type: str       # person | organization | project | concept
    aliases: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class Relationship:
    """Arista del grafo, con temporalidad y evidencia.

    La temporalidad (valid_from / valid_to) permite distinguir
    "esto era cierto en marzo" de "esto sigue siendo cierto hoy".
    """

    id: str
    source_id: str
    target_id: str
    rel_type: str          # works_with | leads | develops | sponsors | discussed_in | ...
    valid_from: str | None = None
    valid_to: str | None = None
    confidence: str = "probable"
    source_doc: str | None = None


@dataclass
class KnowledgeObject:
    """Unidad atómica de conocimiento extraída de un documento."""

    id: str
    ko_type: str
    title: str
    statement: str
    date: str
    people: list[str] = field(default_factory=list)
    project: str | None = None
    status: str = "active"
    confidence: str = "probable"
    source_doc: str | None = None
    tags: list[str] = field(default_factory=list)
    valid_from: str | None = None
    valid_to: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class ContextPack:
    """Paquete de contexto mínimo y relevante que el Context Engine
    construye antes de pasar una pregunta al LLM."""

    query: str
    intent: str
    entities: list[Entity] = field(default_factory=list)
    knowledge_objects: list[KnowledgeObject] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    entity_names: dict = field(default_factory=dict)   # id → nombre legible
    notes: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"# Context pack", f"- Pregunta: {self.query}", f"- Intent: {self.intent}", ""]
        if self.entities:
            lines.append("## Entidades relevantes")
            for e in self.entities:
                lines.append(f"- **{e.name}** ({e.entity_type})")
            lines.append("")
        if self.relationships:
            lines.append("## Relaciones")
            for r in self.relationships:
                window = f" [{r.valid_from or '?'} → {r.valid_to or 'vigente'}]"
                src = self.entity_names.get(r.source_id, r.source_id)
                tgt = self.entity_names.get(r.target_id, r.target_id)
                lines.append(f"- {src} —{r.rel_type}→ {tgt}{window}")
            lines.append("")
        if self.knowledge_objects:
            lines.append("## Knowledge objects")
            for ko in self.knowledge_objects:
                who = f" · {', '.join(ko.people)}" if ko.people else ""
                proj = f" · proyecto: {ko.project}" if ko.project else ""
                lines.append(
                    f"- [{ko.ko_type} · {ko.date} · {ko.status}/{ko.confidence}] "
                    f"**{ko.title}** — {ko.statement}{who}{proj} "
                    f"(fuente: {ko.source_doc or 'desconocida'})"
                )
            lines.append("")
        if self.documents:
            lines.append("## Documentos fuente")
            for d in self.documents:
                lines.append(f"- {d.date} · {d.doc_type} · **{d.title}** ({d.path})")
            lines.append("")
        if self.notes:
            lines.append("## Notas del sistema")
            lines.extend(f"- {n}" for n in self.notes)
            lines.append("")
        return "\n".join(lines)
