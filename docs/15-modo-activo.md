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

## Al día solo: `sb refresh` y `sb schedule`

`sb refresh` es el único comando que necesitas recordar. Corre en orden,
tolerando fallos por paso (un conector caído no detiene a los demás):

```
sources → google (Calendar + Drive) → mail (triaje, metadatos) → areas → enrich → brief
```

- Lock en `.brain/state/refresh.lock` (dos refresh no se solapan), resumen
  en `.brain/state/last_refresh.json`, log diario en `.brain/logs/`.
- `--skip mail`, `--skip google`… omiten un paso; `--quiet` para el servicio.
- El brief queda en `.brain/reports/brief-*.md` y en
  `.brain/state/latest-brief.md`; la pestaña **Hoy** lo muestra con la
  línea «última sincronización hace N min» y el botón **Actualizar ahora**
  (`POST /api/refresh`, corre en segundo plano sin bloquear la UI).

```bash
sb refresh                       # a mano, cuando quieras
sb schedule install --every 4h   # tarea programada nativa, sin admin ni nube
sb schedule status | remove
```

`schedule` escribe el programador de tu sistema: **Windows** dos tareas de
`schtasks` (cada N minutos + al iniciar sesión); **macOS** un LaunchAgent
(`~/Library/LaunchAgents/cl.segundocerebro.refresh.plist`, `StartInterval`);
**Linux** una línea de `crontab` etiquetada. `--dry-run` muestra sin tocar
nada. El acceso directo del escritorio (`sb desktop`) también lanza un
`refresh` en segundo plano antes de abrir la UI: al encender el equipo ya
tienes el brief del día.

## Extracción por área: local por defecto, Claude donde importa

Todo documento entra con la heurística local (rápido, sin red) y queda
marcado con `metadata.extractor`. `sb enrich` hace la **segunda pasada** con
Claude solo sobre las áreas habilitadas: borra los KOs y relaciones
heurísticos de cada documento y los reemplaza por la extracción semántica
(las entidades se conservan). `refresh` lo invoca respetando
`llm.max_docs_per_run`.

```bash
sb config llm --areas academia falp   # habilita Claude en esas áreas
sb config llm --areas clinica         # ✘ rechazado: está en llm.never
sb enrich --dry-run                   # qué está pendiente, sin llamar a Claude
sb enrich --area academia --limit 20
```

Sin `ANTHROPIC_API_KEY` el paso se omite con aviso y la memoria sigue 100 %
local. En la UI (pestaña **Fuentes**, «extracción con claude por área») las
casillas escriben la misma configuración; **clínica aparece deshabilitada**
y el servidor rechaza cualquier intento de activarla (`403`).

## Gmail: metadatos siempre, captura manual cuando importa

El triaje (`sb agent mail`, y el paso `mail` de `refresh`) sigue sin
guardar correos: `latest-triage.json` lleva remitente, asunto, prioridad,
razones y ahora el **id** del mensaje — nunca cuerpo ni snippet. Cuando un
correo sí merece entrar a la memoria, lo capturas **tú, uno a uno**:

```bash
sb mail capture 18f2a9c0b7d3e4f5 --account falp
```

o el enlace **«Capturar a la memoria»** de la pestaña **Correo** (P1–P3).
La captura trae ese único mensaje con cuerpo (`gmail.fetch_message`), lo
guarda como nota Markdown con frontmatter en `.brain/captured/` y lo pasa
por la misma capa cognitiva que cualquier documento (heurística; Claude
después vía `enrich` si el área está habilitada). Es el **único camino** por
el que texto de correo entra al cerebro; duplicados se detectan por
contenido.

## Proyectos especiales: la tesis como hitos, atrasos y próximos pasos

`brain/self/projects.md` (frontmatter, como `areas.md`) define cada proyecto
con área, `start`, `deadline`, personas e **hitos** con fecha. Y tu plan de
trabajo en Excel se convierte en compromisos con vencimiento:

```bash
sb project import-plan PlanTrabajo_VPH_3meses.xlsx --project tesis --start 2026-04-06
sb project          # estado: hechas/total, atrasadas, vencen en 7 días, próximo hito
sb week --save      # revisión semanal → .brain/reports/semana-*.md
```

El importador recorre todas las hojas y se queda con la que más actividades
aporta (p. ej. «Actividades Detalladas», no la portada ni el Gantt); entiende
columnas *Actividad · Sem. · Inicio · Fin · Estado · Responsable ·
Entregable · Prioridad* y convierte `S1, S2…` en fechas a partir de
`--start`. Ids deterministas: **reimportar reemplaza, no duplica**; el Excel
queda ligado como fuente de cada compromiso.

Efectos en la gestión activa:
- `sb today` y la pestaña **Hoy** ganan la sección **Proyectos especiales**:
  días a la entrega, avance, próximo hito, ⚠ atrasadas, vence esta semana.
- `sb week` (y la vista **Semana** de la pestaña Hoy): decisiones de la
  semana, compromisos cerrados/atrasados/próximos, hitos a 14 días,
  preguntas sin resolver hace más de 30 días, correo P1-P2.
- La prioridad de áreas suma la señal `atrasadas × 5`: un proyecto con
  atrasos sube su área en el ranking.

## Puesta en marcha en tu equipo

```bash
git pull && pip install -e ".[files,google]"
sb sources suggest --apply          # carpetas del escritorio y estándar
sb google suggest --apply           # calendarios y carpetas de Drive por cuenta
sb people                           # fija a tus personas clave
sb config llm --areas academia falp # Claude solo ahí (clinica nunca)
sb project import-plan <plan.xlsx> --project tesis --start <YYYY-MM-DD>
sb refresh && sb schedule install --every 4h
sb serve                            # o el acceso directo del escritorio
```
