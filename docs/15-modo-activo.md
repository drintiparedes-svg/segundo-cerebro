# 15 · Modo activo: el cerebro como gestor de tu trabajo diario

Del "memoria que responde" al "cerebro que te ayuda a llevar el día": te
sugiere qué conectar, a quién seguir de cerca, se mantiene al día solo y
convierte tus proyectos especiales (la tesis) en hitos, atrasos y próximos
pasos. Decisiones de diseño acordadas:

- **Un solo usuario, todo en tu equipo.** Nada de multiusuario ni servidor
  compartido; `.brain/` sigue siendo el único lugar donde se escribe.
- **Gmail: metadatos + captura manual.** El triaje nunca persiste correos;
  si uno importa, tú lo capturas explícitamente y solo ese texto entra.
- **Automático, pero local.** Un servicio programado en tu notebook
  sincroniza, triaja y genera el brief. Sin nube.
- **Extracción local por defecto; Claude solo donde tú digas.** Heurística
  para todo; Claude en las áreas que marques (p. ej. `academia`, `falp`).
  `clinica` está prohibida por defecto — línea roja clínica. Nada se usa
  para entrenar.

## Asesor de fuentes: qué carpetas conectar

`sb sources suggest` recorre tu escritorio y las carpetas estándar
(Documentos, Descargas, OneDrive, Google Drive local) **sin abrir ningún
archivo** — solo nombres, tamaños y fechas — y puntúa cada subcarpeta:

| Señal | Peso |
|---|---|
| archivos soportados (md, txt, pdf, docx, xlsx, pptx, csv, vtt…) | hasta 40 |
| modificados en los últimos 90 días | ×3, hasta 30 |
| nombre de carpeta/archivos que calzan con tu mapa de áreas | ×5, hasta 30 |

Veredictos: **conectar** (≥5 archivos soportados y actividad o área clara),
**revisar** (pocas señales; decides tú) e **ignorar** (fotos, binarios,
instaladores, `node_modules`). Tus decisiones se recuerdan en
`.brain/sources.json` (`sources` e `ignored`), así el asesor no insiste.

```bash
sb sources suggest              # tabla con veredicto y razones
sb sources suggest --apply      # una a una: Enter acepta «conectar», n ignora
sb sources sync --no-llm        # trae lo nuevo a la memoria
```

En la UI, pestaña **Fuentes**: subida de archivos, carpetas conectadas con
su última sincronización y el asesor con botones **Conectar / Ignorar**.

### Drive y Calendar: qué seguir por cuenta

`sb google suggest --apply` lista, por cuenta, tus **calendarios** y las
**carpetas de primer nivel de Drive** (solo nombres) y guarda tu elección en
`.brain/google/state-<alias>.json`. Desde entonces `sb google sync` recorre
los calendarios elegidos (antes solo `primary`) y acota Drive a esas
carpetas. También imprime filtros `--query` sugeridos por área, construidos
con los proyectos y palabras clave de `brain/self/areas.md`.

## Personas clave: ranking automático + pin manual

`sb people` ordena a las personas de tu grafo por relevancia:

```
score = relaciones·2 + menciones_30d·3 + reuniones_próximas·5 + correos_P1P2·4
```

y sugiere fijar a las de más señales. El pin es tu validación y vive en
`.brain/people_overrides.json` (con rol, área y nota opcionales):

```bash
sb people                                   # ranking + sugerencias
sb people pin "Ricardo" --role "Gerente clínico" --area falp
sb people unpin "Ricardo"
```

Efectos de fijar a alguien:
- **Correo:** +30 puntos en el triaje heurístico para sus correos (y la
  lista de fijados viaja en el prompt cuando usas Claude).
- **Brief del día:** sección **Personas clave** con su próxima reunión,
  compromisos abiertos y preguntas pendientes con esa persona.
- **Grafo:** su nodo lleva un anillo acento; en la UI, pestaña **Personas**
  con 📌 por tarjeta.

El ranking también lista **remitentes frecuentes fuera del grafo** (solo el
nombre, tomado del último triaje) para que decidas si agregarlos.

## Configuración local

`.brain/config.json` (se crea con valores por defecto):

```json
{
  "refresh": {"every_hours": 4, "triage_days": 7, "days_back": 30, "days_forward": 30},
  "llm": {"default": "local", "areas": [], "never": ["clinica"], "max_docs_per_run": 40},
  "advisor": {"recent_days": 90, "max_files_per_folder": 5000, "max_depth": 4}
}
```

`llm.never` siempre gana sobre `llm.areas`: aunque marques `clinica`, el
sistema la rechaza.

## Privacidad (sin cambios de fondo)

Todo lo anterior es local. Lo único que sale de tu equipo sigue siendo lo
que ya salía: consultas a Google con permisos de solo lectura y, si activas
Claude en un área, el texto de esos documentos hacia la API (sin
entrenamiento). El asesor de carpetas no abre archivos; las sugerencias de
remitentes no incluyen contenido de correo.
