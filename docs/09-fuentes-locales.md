# 9 · Fuentes locales y acceso directo de escritorio

Convierte las carpetas de tu máquina — típicamente las del escritorio — en
fuentes de información del segundo cerebro, con una regla dura:
**solo lectura**. El conector abre archivos exclusivamente para leerlos;
nunca crea, modifica ni borra nada dentro de una fuente (hay una prueba
automatizada que verifica que la carpeta queda bit a bit idéntica tras
sincronizar). Todo lo que el sistema escribe vive en `.brain/`.

## Configuración en un comando

```bash
sb desktop
```

Esto hace tres cosas:

1. **Detecta tu escritorio** (Windows —incluye OneDrive—, macOS y Linux,
   con `Desktop`/`Escritorio`). Si falla: `sb desktop --path <ruta>`.
2. **Registra cada carpeta del escritorio** como fuente de solo lectura
   (una entrada por carpeta; se quitan individualmente con
   `sb sources remove <ruta>`). Los archivos sueltos del escritorio no se
   incluyen; si los quieres: `sb sources add ~/Desktop`.
3. **Crea el acceso directo «Segundo Cerebro»** en el escritorio: al
   abrirlo levanta el servidor local y abre la UI del grafo en el
   navegador (`.bat` en Windows, `.command` en macOS, `.sh` en Linux).

Luego, la primera sincronización:

```bash
sb sources sync --no-llm    # rápida y sin costo (extracción heurística)
sb sources sync             # con extracción semántica de Claude
```

## Gestión de fuentes

```bash
sb sources add ~/Documentos/Papers --alias Papers
sb sources list
sb sources remove ~/Escritorio/Fotos
sb sources sync
```

## Qué se lee

| Tipo | Requisito |
|---|---|
| `.md`, `.txt`, `.csv` | siempre |
| `.pdf`, `.docx` | `pip install -e ".[files]"` |
| imágenes, videos, ejecutables, `.lnk` | se ignoran |

Límites y filtros: archivos > 15 MB se omiten; se saltan carpetas ocultas,
`.git`, papeleras y archivos temporales (`~$…`, `Thumbs.db`, `.DS_Store`).

La sincronización es **incremental** (cursor por fecha de modificación) e
**idempotente** (deduplicación por hash de contenido): puedes agregarla a
un cron junto a `sb google sync`.

## Nota sobre el acceso directo

Crear el acceso directo escribe UN archivo nuevo en el escritorio (el
lanzador). Es lo único que el sistema deja ahí; el contenido de tus
carpetas no se toca.
