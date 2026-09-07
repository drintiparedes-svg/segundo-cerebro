# 12 · Mapa mental de decisiones (Fase 4)

Responde la pregunta que motivó esta fase: **"¿por qué tomé esta decisión
y no otra?"** — reconstruida desde la memoria, lista para explicarla a un
comité o directorio. Todo se calcula **localmente**; ninguna llamada
externa.

## `sb why`

```bash
sb why "base oncohematológica"
sb why "OMOP" --save          # guarda el dossier en .brain/reports/
```

El dossier reconstruye:

| Sección | De dónde sale |
|---|---|
| La decisión | statement, fecha, estado, confianza, personas, proyecto, área |
| Evidencia / origen | el documento fuente (reunión, nota) que la generó |
| Cadena de decisiones | decisiones previas (←) y posteriores (→) del mismo proyecto/área |
| Compromisos derivados | tareas nacidas en el mismo documento |
| Lo que quedó abierto | preguntas sin resolver al momento de decidir |
| Hipótesis relacionadas | hipótesis conectadas por texto |

La búsqueda tolera variaciones morfológicas («oncohematológica» encuentra
«oncohematológicos») vía coincidencia por prefijos.

## En el grafo

Las decisiones ahora son **nodos rombo** en el mapa (color propio),
conectadas a:

- las **personas** que decidieron (`decided`),
- el **proyecto** que moldean (`shapes`),
- la **decisión anterior** del mismo proyecto (`precedes`) — la cadena
  cronológica visible.

Clic en un rombo → el dossier completo en el panel (`/api/why`).

## Cómo se alimenta el mapa

El mapa es tan bueno como el registro. La convención mínima en cualquier
nota:

```
DECISIÓN: <qué se decidió>, porque <rationale>.
```

Con extracción Claude activada, también captura decisiones no marcadas y
sus alternativas descartadas. Para relaciones explícitas entre decisiones
(`supersedes`, `depends_on`) está planificada la extensión del extractor
en la iteración siguiente de esta fase.
