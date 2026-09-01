# Segundo Cerebro — Personal Cognitive OS

Un segundo cerebro para trabajo con rigurosidad, calidad y productividad.
No es "Obsidian con RAG": es una **memoria digital persistente** (episódica,
semántica, relacional, decisional) sobre la que opera una capa de
razonamiento — y, en su versión final, una red de agentes con aprobación
humana.

```text
Captura → Procesamiento cognitivo → Memorias → Router → Context Engine → Razonamiento → Acción → Learning loop
```

## Documentación

| Doc | Contenido |
|---|---|
| [01 · Arquitectura funcional](docs/01-arquitectura-funcional.md) | las 7 capas y el ciclo observe→act |
| [02 · Arquitectura técnica](docs/02-arquitectura-tecnica.md) | stack por versión, componentes V1, seguridad |
| [03 · Modelo de datos](docs/03-modelo-de-datos.md) | knowledge objects, grafo, temporalidad |
| [04 · Estructura de memoria](docs/04-estructura-de-memoria.md) | seis memorias + memory router + context engine |
| [05 · Flujo de agentes](docs/05-flujo-de-agentes.md) | orquestador, approval gate, learning loop |
| [06 · Roadmap](docs/06-roadmap.md) | V1 Memory OS → V4 Agentic Second Brain |
| [07 · Conectores Google](docs/07-conectores-google.md) | Drive + Calendar multi-cuenta (OAuth readonly) |

## Quickstart

```bash
pip install -e .            # o: pip install -e ".[llm]" para extracción/respuestas con Claude
sb ingest brain/            # ingesta el vault (usa --no-llm para modo heurístico)
sb ask "¿Qué decidimos sobre la base oncohematológica?"
sb ask --context-only "…"   # inspecciona el context pack sin LLM
sb tasks                    # compromisos abiertos
sb decisions                # decision ledger
sb timeline                 # memoria episódica
sb serve                    # UI web: grafo de conocimiento en http://127.0.0.1:8765
```

### Conectar tus cuentas Google (Drive + Calendar)

```bash
pip install -e ".[google]"
sb google connect personal   # un alias por cada correo Gmail (abre el navegador)
sb google connect falp
sb google sync               # Calendar ±30 días + Drive incremental, todas las cuentas
```

Configuración de la credencial OAuth (una vez):
[docs/07-conectores-google.md](docs/07-conectores-google.md).

Con credenciales de Claude (`ANTHROPIC_API_KEY` o perfil de `ant auth login`)
la ingesta extrae conocimiento semánticamente y `sb ask` responde citando
fuentes; sin credenciales, todo funciona en modo heurístico/local.

## El vault

`brain/` es la interfaz humana (Markdown puro, editable a mano); la memoria
estructurada vive en `.brain/brain.db` (SQLite en V1; esquema PostgreSQL +
pgvector objetivo en [`db/schema.sql`](db/schema.sql)). Convenciones de
escritura y frontmatter: [`brain/README.md`](brain/README.md).

> **Privacidad:** el contenido personal del vault y la base local están en
> `.gitignore`. El repo versiona código, plantillas y una nota de ejemplo
> sintética.

## UI

`sb serve` levanta el frontend: un grafo de conocimiento force-directed
(canvas, sin dependencias) con paneles de decisiones, compromisos, timeline
y consulta a la memoria. Sin datos propios aún, carga un modo demo.

## Tests

```bash
python -m pytest
```
