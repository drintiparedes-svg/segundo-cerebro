# 11 · Áreas de trabajo y el brief del día (Fase 1)

Primera fase del segundo cerebro operativo: el sistema **identifica las
áreas de tu trabajo** y organiza todo alrededor de ellas — con una regla
dura: la clasificación corre **100% en tu máquina**, por palabras clave,
personas y proyectos. Ninguna llamada externa.

## El mapa de áreas

Vive en [`brain/self/areas.md`](../brain/self/areas.md): tu taxonomía
personal, editable a mano. Cada área define `keywords`, `people` y
`projects`; el clasificador puntúa (proyecto +4, persona +3, palabra +2)
y ante señal insuficiente deja el ítem **sin área** — preferible a
clasificarlo mal.

```bash
sb areas            # tabla: docs, KOs, tareas y decisiones por área
sb areas assign     # re-clasifica toda la memoria (tras editar el mapa)
```

La clasificación es **recalculable**: cambia el mapa, re-ejecuta, y toda
la memoria histórica se reorganiza. Además corre sola después de cada
`sb ingest`, `sb sources sync` y `sb google sync`.

## El brief del día

```bash
sb today            # imprime el brief
sb today --save     # lo guarda en .brain/reports/
```

Cruza, agrupado por área y solo desde la memoria local: agenda de los
próximos días (Calendar sincronizado), *prep* de las reuniones de hoy
(compromisos y decisiones abiertas con cada asistente), tareas abiertas,
correo P1–P2 del último triaje y preguntas sin resolver.

Automatización sugerida (cron, ~7:00):

```
0 7 * * 1-5  cd /ruta/segundo-cerebro && sb google sync --no-llm && sb agent mail --no-llm && sb today --save
```

## En la UI

`sb serve` abre ahora en la pestaña **Áreas**: una tarjeta por área con
sus conteos. La ruta `/api/areas` sirve los datos desde la memoria local.

## Privacidad de esta fase

- Clasificación heurística local: **cero** llamadas a APIs.
- `brain/self/areas.md` versionado solo con la taxonomía profesional
  general; los detalles sensibles que agregues quedan bajo tu control
  (el vault personal completo sigue fuera de git).
- `sb today` se genera y guarda únicamente en `.brain/` local.
