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
