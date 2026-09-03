"""Áreas de trabajo: la taxonomía personal sobre la que se organiza todo.

El mapa vive en brain/self/areas.md (editable a mano, interfaz humana).
La clasificación es 100% LOCAL: puntaje por palabras clave, personas y
proyectos — ninguna llamada externa. Los datos no salen del equipo.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_AREAS_FILE = os.environ.get("SB_AREAS", "brain/self/areas.md")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


@dataclass
class Area:
    id: str
    name: str
    keywords: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)


def load_areas(path: str | Path = DEFAULT_AREAS_FILE) -> list[Area]:
    p = Path(path)
    if not p.exists():
        return []
    m = FRONTMATTER_RE.match(p.read_text(encoding="utf-8"))
    if not m:
        return []
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return []
    areas = []
    for raw in data.get("areas", []):
        if not raw.get("id") or not raw.get("name"):
            continue
        areas.append(Area(
            id=str(raw["id"]),
            name=str(raw["name"]),
            keywords=[str(k).lower() for k in raw.get("keywords", [])],
            people=[str(x) for x in raw.get("people", [])],
            projects=[str(x) for x in raw.get("projects", [])],
        ))
    return areas


def classify(text: str, people: list[str], project: str | None,
             areas: list[Area]) -> str | None:
    """Asigna el área con mejor puntaje. Personas y proyectos pesan más que
    palabras sueltas; sin señal suficiente devuelve None (mejor sin área
    que mal clasificado)."""
    low = text.lower()
    people_low = [p.lower() for p in people]
    project_low = (project or "").lower()

    best_id, best_score = None, 0
    for area in areas:
        score = 0
        for kw in area.keywords:
            if kw in low:
                score += 2
        for person in area.people:
            pl = person.lower()
            if any(pl in x or x in pl for x in people_low) or pl in low:
                score += 3
        for proj in area.projects:
            jl = proj.lower()
            if jl and (jl in project_low or jl in low):
                score += 4
        if score > best_score:
            best_id, best_score = area.id, score
    return best_id if best_score >= 2 else None


def assign_all(store, areas: list[Area]) -> dict:
    """Etiqueta toda la memoria. Idempotente y recalculable: re-ejecutar
    con un mapa de áreas actualizado re-clasifica todo."""
    summary = {"documents": 0, "kos": 0, "unassigned": 0}
    for doc in store.list_documents(limit=100_000):
        meta = doc.metadata
        people = meta.get("people") or []
        if isinstance(people, str):
            people = [people]
        area = classify(
            f"{doc.title}\n{doc.path}\n{doc.body[:3000]}",
            people, meta.get("project"), areas,
        )
        if area != doc.area:
            store.set_document_area(doc.id, area)
        summary["documents"] += 1
        if area is None:
            summary["unassigned"] += 1

    for ko in store.list_knowledge_objects(limit=100_000):
        source = store.get_document(ko.source_doc) if ko.source_doc else None
        area = (source.area if source and source.area else None) or classify(
            f"{ko.title}\n{ko.statement}", ko.people, ko.project, areas)
        if area != ko.area:
            store.set_ko_area(ko.id, area)
        summary["kos"] += 1
    return summary
