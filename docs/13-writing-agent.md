# 13 · Writing agent: documentos desde tu memoria (Fase 3)

Genera borradores de tus documentos recurrentes a partir de lo que la
memoria ya sabe — con **autonomía nivel 2 sin excepciones**: el agente
siempre entrega un borrador para tu revisión en `.brain/drafts/` (local,
fuera de git) y jamás envía ni publica nada.

## Uso

```bash
sb draft --list                       # plantillas disponibles
sb draft onepager --topic "Smart Packaging VPH" --area academia
sb draft informe-gestion --topic "avance mensual" --area falp
sb draft minuta --topic "comité de datos" --no-llm
```

## Las plantillas

Derivadas de tus formatos reales (one-pager y planes de la tesis VPH,
informes de clase) y editables en `brain/templates/drafts/*.md`:

| Plantilla | Estructura |
|---|---|
| `onepager` | problema con cifra dura → concepto por capas → metodología → innovación/impacto → entregables → ficha |
| `informe-academico` | abstract → problema con evidencia → métodos y SRQs → fases → ética/alcance → referencias con [Verificar] |
| `plan-trabajo` | tabla semana × fase × actividades × output verificable + hitos y riesgos |
| `minuta` | contexto → decisiones con rationale → compromisos con plazo → pendientes |
| `informe-gestion` | resumen ejecutivo → avances por proyecto → decisiones del período → riesgos → compromisos abiertos |

Agregar una plantilla nueva = crear otro `.md` con `{{TOPIC}}` y
`{{MATERIAL}}`; aparece sola en `sb draft --list`.

## De dónde sale el contenido

El agente reúne desde la memoria (filtrable por `--area`): decisiones,
compromisos, eventos, preguntas abiertas, literatura y extractos de
documentos — **todo con su fuente citada**.

| Modo | Qué hace | Qué viaja |
|---|---|---|
| `--no-llm` | plantilla + material ordenado por sección, para completar a mano | **nada** |
| Claude (default con credenciales) | redacta el borrador completo usando SOLO el material, cita fuentes y marca `[FALTA: …]` donde no hay datos | los extractos de memoria del tema |

## Línea roja clínica

Ningún dato identificable de pacientes entra a la memoria ni a los
borradores. Los documentos clínicos se generan como estructura +
evidencia; el dato del paciente se completa en el sistema institucional.
El prompt del agente instruye reemplazar cualquier dato clínico que
aparezca por `[DATO CLÍNICO — completar en el sistema institucional]`.
