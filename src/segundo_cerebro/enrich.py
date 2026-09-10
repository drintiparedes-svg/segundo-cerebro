"""Segunda pasada de extracción con Claude, solo en las áreas que tú marques.

Todo documento entra primero con la heurística local (rápido, sin red).
`enrich` toma los documentos de las áreas permitidas en .brain/config.json
que aún no pasaron por Claude, borra sus KOs/relaciones heurísticos y los
reemplaza por la extracción semántica. `llm.never` (clinica por defecto)
siempre gana. Sin credenciales, el paso se omite con aviso: nunca falla.
"""

from __future__ import annotations

from pathlib import Path

from .config import llm_areas, load_config


def enrich(store, brain_dir: str | Path, areas: list[str] | None = None,
           limit: int | None = None, extractor=None, dry_run: bool = False) -> dict:
    from .areas import assign_all, load_areas
    from .ingest import new_summary, process_document

    cfg = load_config(brain_dir)
    allowed = llm_areas(cfg)
    if areas:
        never = set(cfg["llm"].get("never", []))
        blocked = [a for a in areas if a in never]
        if blocked:
            return {"skipped": f"área(s) prohibida(s) para Claude: {', '.join(blocked)}",
                    "enriched": 0}
        allowed = [a for a in areas if a in allowed] or []
    if not allowed:
        return {"skipped": "sin áreas habilitadas para Claude "
                           "(sb config llm --areas academia falp)", "enriched": 0}

    if extractor is None and dry_run:
        limit = limit or int(cfg["llm"].get("max_docs_per_run", 40))
        docs = store.documents_for_enrich(allowed, limit=limit)
        return {"enriched": 0, "pending": len(docs), "areas": allowed,
                "docs": [{"id": d.id, "title": d.title, "area": d.area} for d in docs]}
    if extractor is None:
        from .llm import llm_available
        if not llm_available():
            return {"skipped": "sin credenciales de Claude (ANTHROPIC_API_KEY); "
                               "la memoria sigue en modo local", "enriched": 0,
                    "areas": allowed}
        from .extract import ClaudeExtractor
        extractor = ClaudeExtractor()

    limit = limit or int(cfg["llm"].get("max_docs_per_run", 40))
    docs = store.documents_for_enrich(allowed, limit=limit,
                                      done_by=type(extractor).__name__)
    if dry_run:
        return {"enriched": 0, "pending": len(docs), "areas": allowed,
                "docs": [{"id": d.id, "title": d.title, "area": d.area} for d in docs]}

    summary = new_summary(extractor)
    removed = {"kos": 0, "relationships": 0}
    for doc in docs:
        gone = store.delete_derived(doc.id)
        removed["kos"] += gone["kos"]
        removed["relationships"] += gone["relationships"]
        process_document(store, doc, extractor, summary)
        summary["documents"] += 1
    area_map = load_areas()
    if area_map and docs:
        assign_all(store, area_map)
    return {"enriched": len(docs), "areas": allowed, "removed": removed,
            "knowledge_objects": summary["knowledge_objects"],
            "entities": summary["entities"],
            "relationships": summary["relationships"],
            "extractor": summary["extractor"]}
