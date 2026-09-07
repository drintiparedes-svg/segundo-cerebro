"""`sb why` — el mapa mental de una decisión, reconstruido desde la memoria.

Responde: qué se decidió, cuándo, con quién, sobre qué evidencia, qué
decisiones la precedieron o siguieron, qué quedó abierto y qué tareas
derivaron. Todo se reconstruye LOCALMENTE desde la memoria estructurada;
ninguna llamada externa.
"""

from __future__ import annotations

from dataclasses import asdict


def find_decision(store, query: str):
    """La decisión que mejor calza con la consulta (búsqueda local)."""
    hits = [k for k in store.search_knowledge_objects(query, limit=30)
            if k.ko_type == "decision"]
    if hits:
        return hits[0]
    # sin match FTS exacto: coincidencia por prefijos (tolera variaciones
    # morfológicas: «oncohematológica» calza con «oncohematológicos»)
    prefixes = [t.lower()[:6] for t in query.split() if len(t) > 3]
    if not prefixes:
        return None
    for ko in store.list_knowledge_objects(ko_type="decision", limit=200):
        haystack = (f"{ko.title} {ko.statement} {ko.project or ''} "
                    f"{' '.join(ko.people)}").lower()
        if any(pref in haystack for pref in prefixes):
            return ko
    return None


def build_dossier(store, query: str) -> dict | None:
    decision = find_decision(store, query)
    if decision is None:
        return None

    source = store.get_document(decision.source_doc) if decision.source_doc else None

    # cronología: decisiones del mismo proyecto o área, antes y después
    siblings = []
    if decision.project:
        siblings = store.list_knowledge_objects(
            ko_type="decision", project=decision.project, limit=50)
    if len(siblings) < 2 and decision.area:
        siblings = store.list_knowledge_objects(
            ko_type="decision", area=decision.area, limit=50)
    timeline = sorted((s for s in siblings if s.id != decision.id),
                      key=lambda k: k.date)
    before = [s for s in timeline if s.date <= decision.date][-3:]
    after = [s for s in timeline if s.date > decision.date][:3]

    # del mismo documento fuente: contexto, preguntas y tareas derivadas
    same_doc = [k for k in store.list_knowledge_objects(limit=2000)
                if k.source_doc and k.source_doc == decision.source_doc
                and k.id != decision.id]
    questions = [k for k in same_doc if k.ko_type == "question"]
    tasks = [k for k in same_doc if k.ko_type == "task"]
    hypotheses = [k for k in store.search_knowledge_objects(decision.title, limit=20)
                  if k.ko_type == "hypothesis"]

    return {
        "decision": asdict(decision),
        "source": {
            "title": source.title, "path": source.path, "date": source.date,
            "doc_type": source.doc_type,
        } if source else None,
        "before": [asdict(k) for k in before],
        "after": [asdict(k) for k in after],
        "questions": [asdict(k) for k in questions],
        "tasks": [asdict(k) for k in tasks],
        "hypotheses": [asdict(k) for k in hypotheses],
    }


def to_markdown(dossier: dict, area_names: dict | None = None) -> str:
    d = dossier["decision"]
    names = area_names or {}
    lines = [
        f"# Por qué: {d['title']}",
        "",
        f"**Decisión** ({d['date']} · {d['status']} · confianza {d['confidence']}):",
        f"> {d['statement']}",
        "",
    ]
    meta = []
    if d.get("people"):
        meta.append(f"Participaron: {', '.join(d['people'])}")
    if d.get("project"):
        meta.append(f"Proyecto: {d['project']}")
    if d.get("area"):
        meta.append(f"Área: {names.get(d['area'], d['area'])}")
    if meta:
        lines += ["· " + " · ".join(meta), ""]

    if dossier.get("source"):
        s = dossier["source"]
        lines += ["## Evidencia / origen",
                  f"- {s['date']} · {s['doc_type']} · **{s['title']}** ({s['path']})", ""]

    if dossier["before"] or dossier["after"]:
        lines.append("## Cadena de decisiones")
        for k in dossier["before"]:
            lines.append(f"- ← {k['date']} · {k['statement']}")
        lines.append(f"- ● **{d['date']} · esta decisión**")
        for k in dossier["after"]:
            lines.append(f"- → {k['date']} · {k['statement']}")
        lines.append("")

    if dossier["tasks"]:
        lines.append("## Compromisos que derivaron")
        lines += [f"- [{k['status']}] {k['statement']}" for k in dossier["tasks"]]
        lines.append("")
    if dossier["questions"]:
        lines.append("## Lo que quedó abierto al decidir")
        lines += [f"- {k['statement']}" for k in dossier["questions"]]
        lines.append("")
    if dossier["hypotheses"]:
        lines.append("## Hipótesis relacionadas")
        lines += [f"- {k['statement']}" for k in dossier["hypotheses"]]
        lines.append("")

    lines += ["---",
              "_Reconstruido localmente desde la memoria; cada pieza cita su fuente._"]
    return "\n".join(lines)
