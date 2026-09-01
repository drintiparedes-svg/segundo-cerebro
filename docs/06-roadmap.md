# 6 · Roadmap

**Principio:** subir de nivel solo cuando el problema de recuperación lo
requiera. Mayor complejidad no significa mejor segundo cerebro.

## V1 — Memory OS ✅ (este repo)

- Vault Markdown (`brain/`) como interfaz humana
- Ingesta idempotente + extracción (Claude o heurística)
- Knowledge objects, entidades, relaciones con temporalidad
- Router de memoria + Context Engine trazable
- CLI `sb` + UI web con grafo de conocimiento
- Respuestas con Claude citando fuentes

**Criterio de salida:** el sistema responde mejor que grep + memoria propia
sobre ≥1 mes de notas reales.

## V2 — Cognitive Memory

- PostgreSQL + pgvector (búsqueda híbrida BM25 + vectorial)
- Conectores: Google Drive, Gmail, Calendar, transcripciones de reuniones
- Perfil de identidad estructurado en el context pack
- Registro de feedback operativo (learning loop real)
- Store cifrado para información sensible; OAuth mínimo privilegio

**Criterio de salida:** captura sin fricción — no depende de escribir notas
a mano para que la memoria crezca.

## V3 — Knowledge Graph

- Modelo de entidades estabilizado → grafo de primera clase
  (consultas recursivas en PG; Neo4j solo si el traversal lo exige)
- Resolución de entidades (alias, duplicados)
- Vistas: timeline por persona/proyecto, decisiones vigentes vs supersedidas

**Criterio de salida:** preguntas relacionales multi-salto ("¿quién puede
presentarme al sponsor de X?") se responden desde el grafo.

## V4 — Agentic Second Brain

- Orquestador + agentes (research, strategy, project, executive, writing)
- Human approval gate para toda acción externa
- Acciones: borradores de correo, preparación de reuniones, informes
- Autonomía gradual por categoría de acción

**Criterio de salida:** al menos un flujo semanal completo (p. ej.
preparación de reunión de gerencia) corre end-to-end con aprobación humana.
