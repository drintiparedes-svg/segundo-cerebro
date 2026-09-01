# Vault — interfaz humana del Segundo Cerebro

Estas carpetas son **la interfaz humana**: Markdown legible y editable a mano.
Por debajo, `sb ingest brain/` convierte cada nota en documentos, knowledge
objects, entidades y relaciones dentro de la memoria estructurada.

```
brain/
├── inbox/       ← captura rápida; todo entra aquí primero
├── self/        ← identidad, objetivos, forma de trabajo, principios
├── people/      ← una nota por persona relevante
├── projects/    ← una nota por proyecto (FALP, Medismart, tesis, …)
├── meetings/    ← una nota por reunión (memoria episódica)
├── decisions/   ← decisiones con rationale (decision ledger)
├── knowledge/   ← conocimiento semántico (IA, salud, diseño, gestión)
└── templates/   ← plantillas (no se ingestan)
```

## Convenciones de escritura

El extractor heurístico reconoce estas marcas (el extractor con Claude las
entiende igual, pero también extrae lo que no esté marcado):

| Marca | Se convierte en |
|---|---|
| `DECISIÓN: ...` | knowledge object tipo `decision` |
| `- [ ] ...` | `task` (compromiso abierto) |
| `PREGUNTA: ...` | `question` (no resuelto) |
| `IDEA: ...` | `idea` |
| `HIPÓTESIS: ...` | `hypothesis` |

## Frontmatter

```yaml
---
title: Reunión gerencia clínica
type: meeting          # meeting | note | decision | paper
date: 2026-08-12
people: [Ricardo, Raimundo]
project: Oncohematology Data Platform
organizations: [FALP]
tags: [oncología, datos-clínicos]
---
```

`people`, `project` y `organizations` alimentan el knowledge graph
automáticamente (persona —participates_in→ proyecto, con fecha).
