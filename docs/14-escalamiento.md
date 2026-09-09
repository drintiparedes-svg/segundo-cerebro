# 14 · Escalamiento: prioridad, subida de documentos, conectores y validación

Cinco capacidades que llevan el sistema de "memoria que responde" a
"memoria que se organiza sola bajo tu control". Reglas intactas: todo
local, fuentes de solo lectura, sin datos de pacientes.

## Prioridad de áreas: jerarquía automática + validación manual

El score se calcula localmente desde señales de la memoria:

```
score = (tareas·3 + eventos_7d·4 + decisiones_14d·2 + preguntas·1 + correo_P1P2·4) × peso
```

Tu validación manual siempre gana: **peso** (multiplica), **pin** (fija
posición) y **pausa** (manda al final). Vive en `.brain/area_overrides.json`.

```bash
sb areas                        # ranking con señales
sb areas set academia --pin 1   # fijar arriba
sb areas set personal --pause   # pausar temporada
sb areas review                 # revisión interactiva del ranking
```

En la UI, la pestaña **Áreas** muestra las tarjetas rankeadas con barra de
score y botones ▲/▼/📌 (escriben en tu servidor local vía
`POST /api/areas/override`; en la demo pública quedan deshabilitados).
`sb today` ordena sus secciones según este ranking.

## Subir documentos del notebook

```bash
sb add informe.docx datos.xlsx --area falp   # archivos sueltos
sb add paper.pdf --copy                      # copia a .brain/uploads/
sb sources add ~/Documentos/Proyectos        # carpetas completas (ya existía)
```

Y en la UI, pestaña **Subir**: arrastra el archivo, se guarda en
`.brain/uploads/`, se procesa y clasifica — todo en tu máquina
(`POST /api/upload`, solo del servidor local).

## Conectores nuevos

| Conector | Comando | Qué entra |
|---|---|---|
| Zotero / BibTeX | `sb zotero import biblioteca.bib` (o CSL-JSON) | referencias como papers, mismo formato que Europe PMC |
| Transcripciones | automático vía `sb sources sync` / `sb add` | `.vtt`/`.srt` y textos con hablantes «Nombre:» entran como reunión con participantes al grafo |
| WhatsApp / Slack | `sb chats import export.txt` / `export.zip` | un documento por día de conversación, participantes al grafo |

Privacidad: los tres son locales; chats y transcripciones jamás salen del
equipo (misma política que el correo).

## Búsqueda y validación de literatura

```bash
sb literature search "HPV self-sampling" --open-only   # Europe PMC → memoria
sb literature verify tesis.docx                        # valida referencias
```

`verify` extrae las referencias (DOIs y entradas numeradas), consulta
**Crossref** y compara título, primer autor y año. Genera un **informe**
en `.brain/reports/verificacion-*.md` con el patrón de tu bibliografía:

```
- [Verificado] Arbyn M. Detecting cervical precancer… doi:10.1136/bmj.k4823
- [Discrepancia] … — año: cita 2021 vs fuente 2018
- [No encontrado] …
```

**Nunca edita el documento original** (regla de solo lectura); corriges tú
a partir del informe. Exit code ≠ 0 si quedan referencias sin verificar —
útil como control previo a una entrega. Lo único que viaja a Crossref son
las citas mismas (datos bibliográficos públicos).
