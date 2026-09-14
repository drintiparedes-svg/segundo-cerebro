# 17 · Carga de trabajo y autonomía supervisada

## Cockpit de carga: hoy y los próximos 7 días

La pregunta que responde: **¿cabe lo que tengo que hacer en el tiempo que
tengo?** Todo se calcula localmente desde tu memoria.

```
capacidad(día)   = jornada (config `workday`, por defecto 08:30–18:00, lun–vie)
agenda(día)      = suma de eventos de Calendar (duración real; 60 min si no se sabe;
                   los de día completo no restan)
foco(día)        = (capacidad − agenda) × focus_ratio (0.6)
```

Cada compromiso abierto tiene un **esfuerzo** en horas, con este orden de
fuentes: el que tú ajustaste → la duración del plan Excel (`5 días` = 20 h
de foco, `90 min` = 1.5 h) → la mediana histórica del proyecto (tareas
cerradas con esfuerzo) → el tipo (tarea 1 h, pregunta 0.5 h).

La **planificación** es greedy y explicable: atrasadas primero, luego lo
que vence antes, luego el área mejor rankeada; cada tarea cae en el primer
día con espacio antes de su vencimiento. Si no cabe entera va a su día
límite (o a hoy, si está atrasada) y ese día queda **⚠ sobrecargado**. Una
semana sin jornada deja tareas **sin espacio**. Las tareas **fijadas** a un
día (`sb task move`, o desde la UI) se respetan.

```bash
sb carga                     # tabla de 7 días con barras, tareas por día e ids
sb task done <id>            # cerrar (también reopen)
sb task effort <id> 2.5      # ajustar esfuerzo
sb task move <id> 2026-09-17 # fijar a un día
sb task due <id> 2026-09-20  # cambiar vencimiento
```

`sb today` gana la sección **Carga de hoy** (agenda + tareas / jornada) y
`sb week` la **Proyección de la semana** (porcentaje por día, sobrecargas y
tareas sin espacio). En la UI, pestaña **Carga**: franja de 7 días con
barras de agenda / tareas / libre, lista por día con esfuerzo editable,
✔ para cerrar y → para mover al día siguiente; `GET /api/workload`,
`POST /api/kos/update`.

Configura tu jornada en `.brain/config.json`:

```json
"workday": {"start": "08:30", "end": "18:00", "days": [1,2,3,4,5],
            "focus_ratio": 0.6, "meeting_default_min": 60}
```

## Matriz de autonomía: qué corre solo, qué se propone, qué nunca

| Nivel | Significa | Ejemplos por defecto |
|---|---|---|
| **L0** observar | leer y registrar | sincronizar fuentes, triaje de correo |
| **L1** sugerir | proponer; tú decides | fijar personas, conectar carpetas |
| **L2** borrador | producto listo para tu revisión, en la bandeja | preparación de reuniones |
| **L3** automático interno | corre solo, con registro y deshacer; nada sale del equipo | clasificar, priorizar, brief, planificar la semana, enriquecer, revisión semanal |
| **L3+** externo de bajo riesgo | automático y reversible, en tus propias cuentas | bloque de foco en Calendar, borrador en Gmail (no enviado) |
| **L4** irreversible | **siempre** aprobación humana; techo L2, la interfaz no deja subirlo | enviar correo, borrar, compartir/publicar, pagar |

```bash
sb autonomy                        # matriz: nivel, techo, clase
sb autonomy set meeting_prep L3    # ✔ dentro del techo
sb autonomy set send_email L3      # ✘ irreversible: techo L2
```

Los niveles viven en `.brain/autonomy.json`. Con la IA apagada (`sb ai off`)
todo se acota a **L2**: nada corre solo. En la UI, pestaña **Auto → Matriz**.

## Bandeja de aprobación

Los agentes **proponen** ítems; la matriz decide: L3/L3+ se ejecutan con
registro y **deshacer**, L2 esperan tu aprobación, L1 quedan como sugerencia.
Todo en `.brain/queue/` y `.brain/logs/actions.log`.

```bash
sb queue                      # pendientes, sugeridos, historial
sb queue approve <id>         # ejecuta (o «manual» si no hay ejecutor: lo haces tú)
sb queue reject <id> --reason "…"
sb queue undo <id>            # borra el evento / borrador / nota que creó
sb flows                      # corre los agentes ahora (también en sb refresh)
```

Ejecutores disponibles (los únicos que tocan algo): nota en `.brain/drafts/`,
evento en **tu** calendario, borrador en **tu** Gmail, revisión semanal.
Todos devuelven lo necesario para deshacer.

## Escritura Google opt-in

Por defecto todo es de solo lectura. Para que los L3+ actúen en tus
cuentas, autoriza explícitamente y por cuenta **solo dos permisos**:

```bash
sb google connect falp --write    # calendar.events + gmail.compose (nunca gmail.send)
```

Sin ese permiso, los ítems externos bajan a la bandeja y, al aprobarlos,
quedan en estado **manual** con los datos para que lo hagas tú.

## Agentes de flujo

| Agente | Cuándo | Qué propone | Nivel por defecto |
|---|---|---|---|
| Preparación de reunión | 24 h antes de cada reunión con asistentes | dossier por persona (pendientes, preguntas), documentos relacionados, agenda propuesta | L2 |
| Bloque de foco | compromiso ≥ 1 h que vence en ≤ 2 días | evento «Foco · …» en el día planificado por Carga | L3+ |
| Respuesta a P1 | correo P1 de una persona fijada | borrador de respuesta con lo pendiente entre ambos (no se envía) | L3+ |
| Revisión semanal | lunes | `sb week` guardado en `.brain/reports/` | L3 |

Cada propuesta tiene una clave única: correr los agentes mil veces no
duplica nada.
