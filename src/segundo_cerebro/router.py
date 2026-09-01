"""Memory Router / Cognitive Router.

Antes de recuperar información, clasifica la pregunta: cada tipo de memoria
se consulta con la tecnología adecuada (no todo pasa por búsqueda vectorial).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

INTENTS = (
    "episodic",     # ¿cuándo pasó X? ¿qué se habló en la reunión?
    "relational",   # ¿quién está vinculado con...? ¿con quién trabaja...?
    "decisional",   # ¿qué decidimos sobre...? ¿por qué se decidió...?
    "commitments",  # ¿qué tengo pendiente? tareas, compromisos
    "semantic",     # ¿qué sé sobre...? conceptos, conocimiento
    "strategic",    # ¿qué debería hacer/discutir...? requiere multi-fuente
)

_PATTERNS: list[tuple[str, list[str]]] = [
    ("strategic", [
        r"\bqu[eé] deber[ií]a\b", r"\bc[oó]mo (deber[ií]a|convendr[ií]a)\b",
        r"\brecomiendas?\b", r"\bpreparar\b.*\breuni[oó]n\b",
        r"\bdiscutir\b", r"\bestrategia\b", r"what should i\b",
    ]),
    ("decisional", [
        r"\bdecid", r"\bacord", r"\bdecisi[oó]n", r"\bpor qu[eé] (se|no)\b",
        r"\brationale\b", r"decision\b", r"agreed\b",
    ]),
    ("commitments", [
        r"\bpendiente", r"\btareas?\b", r"\bcompromisos?\b", r"\bdebo\b",
        r"\btengo que\b", r"\bto-?dos?\b", r"open (tasks|items)\b",
    ]),
    ("relational", [
        r"\bqui[eé]n(es)?\b", r"\bcon qui[eé]n\b", r"\bvinculad", r"\brelacionad",
        r"\btrabaja con\b", r"\bparticipa\b", r"\bequipo\b", r"who (is|works)\b",
    ]),
    ("episodic", [
        r"\bcu[aá]ndo\b", r"\breuni[oó]n", r"\bla [uú]ltima vez\b", r"\bhistorial\b",
        r"\bqu[eé] (pas[oó]|se habl[oó]|se dijo)\b", r"\btimeline\b", r"when did\b",
        r"\bmeeting\b",
    ]),
]


@dataclass
class RoutingDecision:
    intent: str
    memories: list[str]     # qué memorias consultar, en orden
    reason: str


def route(query: str) -> RoutingDecision:
    q = query.lower()
    for intent, patterns in _PATTERNS:
        for p in patterns:
            if re.search(p, q):
                return RoutingDecision(
                    intent=intent,
                    memories=_MEMORY_PLAN[intent],
                    reason=f"patrón «{p}»",
                )
    return RoutingDecision(
        intent="semantic",
        memories=_MEMORY_PLAN["semantic"],
        reason="sin patrón específico: búsqueda semántica por defecto",
    )


_MEMORY_PLAN: dict[str, list[str]] = {
    "strategic": ["graph", "decisions", "commitments", "episodic", "documents"],
    "decisional": ["decisions", "graph", "documents"],
    "commitments": ["commitments", "graph"],
    "relational": ["graph", "episodic"],
    "episodic": ["episodic", "documents", "graph"],
    "semantic": ["documents", "kos", "graph"],
}
