# 10 · Agentes y privacidad

Primera entrega de la capa de agentes (V4 del roadmap): dos agentes que
**leen y recomiendan, nunca actúan**. La privacidad no es una nota al pie:
es la restricción de diseño número uno de esta capa.

## Los agentes

### Curador de archivos — `sb agent organize`

Agrupa todos los documentos de la memoria (vault, carpetas del escritorio,
Drive, Calendar) en colecciones coherentes por proyecto o tema.

```bash
sb agent organize            # clasificación semántica con Claude
sb agent organize --no-llm   # 100% local: agrupa por fuente/carpeta
sb collections               # ver las colecciones
```

- Con Claude viajan **solo** título, ruta, tipo, fecha y un extracto de
  240 caracteres por documento — nunca el contenido íntegro.
- El resultado se guarda en la memoria local (tabla `collections`) y el
  informe en `.brain/reports/`.
- Re-ejecutarlo recalcula la agrupación (no acumula duplicados).

Tipos de archivo legibles: `.md .txt .csv .json .html` siempre;
`.pdf .docx .xlsx .pptx` con `pip install -e ".[files]"`.

### Triaje de correo — `sb agent mail`

Prioriza tu bandeja de Gmail (todas tus cuentas conectadas) en cinco
niveles — P1 urgente → P5 archivar — cruzando cada remitente con tu
knowledge graph: un correo de alguien con quien compartes proyectos pesa
más que cualquier newsletter.

```bash
sb agent mail                       # todas las cuentas, últimos 7 días
sb agent mail --no-llm              # 100% local: nada sale de tu máquina
sb agent mail --account falp --days 3
sb agent mail --query "from:falp.org"
sb agent mail --bodies              # opt-in: incluir el cuerpo completo
```

## Modelo de privacidad

### Qué NO pasa nunca

- **Nada se entrena.** Este sistema no entrena ni ajusta ningún modelo:
  el "learning loop" del roadmap es una base de datos local de
  preferencias (tabla `feedback`), no entrenamiento.
- **Nada se publica.** Correos, archivos e informes viven en `.brain/`
  (local, bloqueado por `.gitignore`). La vitrina de Vercel no tiene
  acceso a nada de esto.
- **Nada se modifica.** Gmail se lee con scope `gmail.readonly` (el token
  no permite enviar, borrar ni marcar) y las carpetas locales con el
  conector de solo lectura verificado por tests.
- **Los correos no entran a la memoria.** El triaje los lee, prioriza y
  descarta; solo queda el informe local en `.brain/reports/`.

### Qué sale de tu máquina, y solo si tú lo decides

| Modo | Qué viaja | A dónde |
|---|---|---|
| `--no-llm` | **nada** | — |
| por defecto (Claude) | correo: remitente, asunto, fecha, snippet · archivos: título, ruta, extracto de 240 chars | API de Anthropic |
| `--bodies` (opt-in) | además, el cuerpo del correo | API de Anthropic |

Sobre la API de Anthropic: bajo sus términos comerciales, los datos
enviados por API **no se usan para entrenar modelos** por defecto y tienen
retención limitada. Aún así, el modo `--no-llm` existe para que la
decisión sea tuya caso a caso; para correo especialmente sensible,
úsalo o filtra con `--query`.

### Defensa en profundidad

1. Scopes mínimos (readonly en Drive, Calendar y Gmail).
2. Tokens OAuth solo en `.brain/google/` (fuera de git).
3. Cuerpo de correos: opt-in explícito, truncado a 20k caracteres.
4. Informes y memoria: solo en `.brain/`, nunca versionados.
5. Los agentes no tienen capacidad de acción externa: el approval gate
   del V4 se implementará antes de darles cualquier acción.

> Nota: si autorizaste tus cuentas Google antes de esta versión, vuelve a
> ejecutar `sb google connect <alias>` una vez para otorgar el permiso de
> lectura de Gmail.
