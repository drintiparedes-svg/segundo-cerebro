---
# Proyectos especiales — los que merecen hitos, atrasos y próximos pasos
# en el brief del día. EDÍTALO A MANO. Fechas en YYYY-MM-DD.
#
#   sb project                      # estado de cada proyecto
#   sb project import-plan PlanTrabajo.xlsx --project tesis --start 2026-04-06
#   sb week                         # revisión semanal
#
# Este archivo es tu interfaz local: si incluye detalles sensibles, evita
# subirlo a repositorios públicos.
projects:
  - id: tesis
    name: MSc Thesis
    area: academia
    start: 2026-04-06
    deadline: 2026-12-15
    people: [Inti]
    keywords: [tesis, thesis, hpv, vph, self-sampling, packaging]
    milestones:
      - { name: "Informe de insights Fase 1", due: 2026-05-03 }
      - { name: "Prototipo packaging + agente IA", due: 2026-06-07 }
      - { name: "Pruebas de usabilidad", due: 2026-06-21 }
      - { name: "Entrega del informe final", due: 2026-12-15 }
---

# Proyectos especiales

Cada proyecto de la lista aparece en `sb today` con su próximo hito, las
actividades atrasadas y las que vencen esta semana. Los compromisos se
importan desde tu plan de trabajo en Excel (`sb project import-plan`) o se
extraen de tus notas y correos como cualquier otro knowledge object.
