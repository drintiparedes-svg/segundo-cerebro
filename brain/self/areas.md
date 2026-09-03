---
# Mapa de áreas de trabajo — la taxonomía personal del segundo cerebro.
#
# EDÍTALO A MANO: agrega/quita áreas, palabras clave, personas y proyectos.
# La clasificación corre 100% en tu máquina (sin llamadas externas).
# Después de editar: sb areas assign
#
# Consejo de privacidad: los detalles sensibles (nombres de terceros,
# proyectos confidenciales) puedes mantenerlos aquí — este archivo es tu
# interfaz local; evita subirlo a repositorios públicos si los incluye.
areas:
  - id: falp
    name: FALP · Informática Médica
    keywords: [falp, oncodata, rhc, oncohematolog, oncolog, ficha clínica, registro hospitalario, prisma]
    people: [Ricardo, Raimundo]
    projects: [ONCODATA, RHC, Oncohematology Data Platform]

  - id: clinica
    name: Clínica · Urología
    keywords: [urolog, endourolog, próstata, prostat, renal, riñón, vejiga, paciente, cirugía, filial]
    people: []
    projects: []

  - id: medismart
    name: MediSmart · Producto
    keywords: [medismart, minuta, transcripción, resumen clínico, telemedicina]
    people: []
    projects: [MediSmart]

  - id: academia
    name: Academia · MSc Imperial
    keywords: [imperial, tesis, thesis, human-ai, paper, publicación, calibration, trust, nejm, pubmed]
    people: []
    projects: [MSc Thesis]

  - id: emprendimiento
    name: Emprendimiento · Asesorías
    keywords: [startup, agente, andes ai, gemini, pitch, corfo, anid]
    people: [Rodrigo]
    projects: []

  - id: personal
    name: Personal · Patrimonio
    keywords: [banco, seguro, isapre, liquidación, boleta, arriendo, propiedad, viaje, familia]
    people: []
    projects: []
---

# Mapa de áreas

Este archivo define **las áreas de tu trabajo**: todo documento, decisión,
tarea, reunión y correo se etiqueta contra ellas. Edita el frontmatter de
arriba y corre `sb areas assign` para re-clasificar toda la memoria.

Reglas de la clasificación (local, sin LLM):
- proyecto coincidente: +4 · persona coincidente: +3 · palabra clave: +2
- si ningún área alcanza puntaje 2, el ítem queda "sin área" (preferible a
  clasificarlo mal); revísalos con `sb areas`.
