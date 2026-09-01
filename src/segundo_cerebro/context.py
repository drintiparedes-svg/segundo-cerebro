"""Context Engine: construye un context pack mínimo y relevante.

Recibe la pregunta ya clasificada por el router y consulta cada memoria en
el orden que éste indica. El resultado es un ContextPack trazable (cada
pieza cita su fuente) que se entrega al LLM — o directamente al usuario.
"""

from __future__ import annotations

from .models import ContextPack, Entity
from .router import RoutingDecision, route
from .store import BrainStore

MAX_KOS = 25
MAX_DOCS = 4


def build_context(store: BrainStore, query: str,
                  routing: RoutingDecision | None = None) -> ContextPack:
    routing = routing or route(query)
    pack = ContextPack(query=query, intent=routing.intent)
    pack.notes.append(f"Router: {routing.intent} ({routing.reason})")

    matched_entities = _match_entities(store, query)
    pack.entities = matched_entities
    entity_names = [e.name for e in matched_entities]

    seen_kos: set[str] = set()

    for memory in routing.memories:
        if memory == "graph":
            for ent in matched_entities:
                pack.relationships.extend(store.relationships_of(ent.id))
        elif memory == "decisions":
            _add_kos(pack, seen_kos, _by_type(store, "decision", entity_names, query))
        elif memory == "commitments":
            _add_kos(pack, seen_kos, _by_type(store, "task", entity_names, query,
                                              status="active"))
        elif memory == "episodic":
            _add_kos(pack, seen_kos, _by_type(store, "event", entity_names, query))
        elif memory == "kos":
            _add_kos(pack, seen_kos, store.search_knowledge_objects(query))
        elif memory == "documents":
            pack.documents = store.search_documents(query, limit=MAX_DOCS)

    # Nombres legibles para las relaciones del pack.
    for rel in pack.relationships:
        for eid in (rel.source_id, rel.target_id):
            if eid not in pack.entity_names:
                ent = store.get_entity(eid)
                if ent:
                    pack.entity_names[eid] = f"{ent.name} ({ent.entity_type})"

    # Preguntas abiertas relacionadas siempre agregan valor al pack.
    _add_kos(pack, seen_kos, _by_type(store, "question", entity_names, query,
                                      status="active"))
    pack.knowledge_objects = pack.knowledge_objects[:MAX_KOS]
    return pack


def _match_entities(store: BrainStore, query: str) -> list[Entity]:
    found: dict[str, Entity] = {}
    for token in query.replace("¿", " ").replace("?", " ").split():
        clean = token.strip(".,;:()").strip()
        if len(clean) < 3 or not clean[0].isupper():
            continue  # heurística V1: entidades nombradas van capitalizadas
        for ent in store.find_entities(clean):
            found[ent.id] = ent
    return list(found.values())


def _by_type(store: BrainStore, ko_type: str, entity_names: list[str],
             query: str, status: str | None = None):
    if entity_names:
        results = []
        for name in entity_names:
            results.extend(store.list_knowledge_objects(
                ko_type=ko_type, person=name, status=status))
        if results:
            return results
    # Sin entidad reconocida: caer a búsqueda por texto filtrada por tipo.
    return [ko for ko in store.search_knowledge_objects(query)
            if ko.ko_type == ko_type and (status is None or ko.status == status)] \
        or store.list_knowledge_objects(ko_type=ko_type, status=status, limit=10)


def _add_kos(pack: ContextPack, seen: set[str], kos) -> None:
    for ko in kos:
        if ko.id not in seen:
            seen.add(ko.id)
            pack.knowledge_objects.append(ko)
