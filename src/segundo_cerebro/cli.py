"""CLI del Segundo Cerebro.

Uso:
    sb ingest brain/               # ingesta el vault completo
    sb ask "¿Qué debería discutir mañana con Ricardo?"
    sb search "confianza humano-IA"
    sb tasks | sb decisions | sb entities | sb timeline
    sb serve                       # UI web (grafo de conocimiento)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .context import build_context
from .ingest import ingest_path
from .router import route
from .store import BrainStore

DEFAULT_DB = os.environ.get("SB_DB_PATH", ".brain/brain.db")


def _store(args) -> BrainStore:
    return BrainStore(args.db)


def cmd_ingest(args) -> int:
    store = _store(args)
    target = Path(args.path)
    if not target.exists():
        print(f"No existe: {target}", file=sys.stderr)
        return 1
    summary = ingest_path(store, target, prefer_llm=not args.no_llm)
    print(f"Extractor: {summary['extractor']}")
    print(f"Documentos nuevos: {summary['documents']} (omitidos: {summary['skipped']})")
    print(f"Knowledge objects: {summary['knowledge_objects']}")
    print(f"Entidades: {summary['entities']} · Relaciones: {summary['relationships']}")
    return 0


def cmd_ask(args) -> int:
    store = _store(args)
    pack = build_context(store, args.question)
    if args.context_only:
        print(pack.to_markdown())
        return 0
    from .llm import answer, llm_available
    if llm_available():
        print(answer(pack))
    else:
        print("(Sin credenciales de Claude: mostrando el context pack)\n")
        print(pack.to_markdown())
    return 0


def cmd_search(args) -> int:
    store = _store(args)
    routing = route(args.query)
    print(f"Intent: {routing.intent} → memorias: {', '.join(routing.memories)}\n")
    for ko in store.search_knowledge_objects(args.query):
        print(f"[{ko.ko_type} · {ko.date}] {ko.title}")
    for doc in store.search_documents(args.query):
        print(f"[doc · {doc.date}] {doc.title} ({doc.path})")
    return 0


def cmd_list(args, ko_type: str) -> int:
    store = _store(args)
    for ko in store.list_knowledge_objects(ko_type=ko_type, status=args.status):
        who = f" · {', '.join(ko.people)}" if ko.people else ""
        print(f"{ko.date} [{ko.status}] {ko.statement}{who}")
    return 0


def cmd_entities(args) -> int:
    store = _store(args)
    for ent in store.list_entities():
        rels = store.relationships_of(ent.id)
        print(f"[{ent.entity_type}] {ent.name} ({len(rels)} relaciones)")
    return 0


def cmd_timeline(args) -> int:
    store = _store(args)
    events = store.list_knowledge_objects(ko_type="event", limit=100)
    for ev in sorted(events, key=lambda e: e.date):
        print(f"{ev.date}  {ev.title}")
    return 0


def cmd_export(args) -> int:
    from .snapshot import write_snapshot
    data = write_snapshot(_store(args), args.output, include_bodies=not args.no_bodies)
    print(f"Snapshot: {args.output}")
    print(f"Entidades: {len(data['nodes'])} · relaciones: {len(data['links'])} · "
          f"KOs: {len(data['kos'])} · documentos: {len(data['documents'])}")
    return 0


def cmd_google_connect(args) -> int:
    from .connectors.google_auth import GoogleAuthError, get_credentials
    try:
        get_credentials(args.alias, interactive=True)
    except GoogleAuthError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Cuenta «{args.alias}» autorizada. Sincroniza con: sb google sync")
    return 0


def cmd_google_accounts(args) -> int:
    from .connectors.google_auth import list_accounts
    accounts = list_accounts()
    if not accounts:
        print("Sin cuentas conectadas. Usa: sb google connect <alias>")
    for alias in accounts:
        print(alias)
    return 0


def cmd_google_sync(args) -> int:
    from .connectors.google_auth import list_accounts
    from .connectors.google_sync import sync_all

    accounts = [args.account] if args.account else list_accounts()
    if not accounts:
        print("Sin cuentas conectadas. Usa: sb google connect <alias>", file=sys.stderr)
        return 1

    summary = sync_all(
        _store(args), accounts=accounts,
        calendar=not args.no_calendar, drive=not args.no_drive,
        days_back=args.days_back, days_forward=args.days_forward,
        drive_query=args.query, prefer_llm=not args.no_llm,
    )
    for alias, info in summary["accounts"].items():
        line = f"[{alias}] calendar: {info['calendar']} · drive: {info['drive']}"
        print(line)
        for err in info["errors"]:
            print(f"[{alias}] ERROR {err}", file=sys.stderr)
    print(f"Documentos nuevos: {summary['documents']} · "
          f"KOs: {summary['knowledge_objects']} · "
          f"entidades: {summary['entities']} · relaciones: {summary['relationships']}")
    return 1 if any(i["errors"] for i in summary["accounts"].values()) else 0


def _brain_dir(args) -> Path:
    return Path(args.db).parent


def cmd_sources_add(args) -> int:
    from .connectors.localfs import add_source
    entry = add_source(_brain_dir(args), args.path, alias=args.alias)
    print(f"Fuente registrada (solo lectura): {entry['alias']} → {entry['path']}")
    return 0


def cmd_sources_list(args) -> int:
    from .connectors.localfs import load_registry
    registry = load_registry(_brain_dir(args))
    if not registry["sources"]:
        print("Sin fuentes locales. Usa: sb sources add <carpeta>  o  sb desktop")
        return 0
    for s in registry["sources"]:
        state = registry["state"].get(s["path"], {})
        last = state.get("last_sync", "nunca sincronizada")
        print(f"{s['alias']:24} {s['path']}  (última sync: {last})")
    return 0


def cmd_sources_remove(args) -> int:
    from .connectors.localfs import remove_source
    ok = remove_source(_brain_dir(args), args.path)
    print("Fuente eliminada del registro." if ok else "Esa ruta no estaba registrada.")
    return 0


def cmd_sources_sync(args) -> int:
    from .connectors.localfs import load_registry, sync_source
    from .extract import get_extractor
    from .ingest import new_summary, process_document

    store = _store(args)
    brain_dir = _brain_dir(args)
    registry = load_registry(brain_dir)
    if not registry["sources"]:
        print("Sin fuentes locales. Usa: sb sources add <carpeta>  o  sb desktop",
              file=sys.stderr)
        return 1

    extractor = get_extractor(prefer_llm=not args.no_llm)
    summary = new_summary(extractor)
    for source in registry["sources"]:
        result = sync_source(store, brain_dir, source)
        if "error" in result:
            print(f"[{source['alias']}] AVISO: {result['error']}", file=sys.stderr)
            continue
        for doc in result["docs"]:
            summary["documents"] += 1
            process_document(store, doc, extractor, summary)
        print(f"[{source['alias']}] nuevos: {result['added']} · "
              f"sin cambios: {result['unchanged']} · "
              f"no soportados: {result['unsupported']}")
    print(f"Total — documentos: {summary['documents']} · KOs: {summary['knowledge_objects']} · "
          f"entidades: {summary['entities']} · relaciones: {summary['relationships']}")
    return 0


def cmd_desktop(args) -> int:
    from .desktop import create_shortcut, find_desktop, register_desktop_folders

    desktop = Path(args.path).expanduser() if args.path else find_desktop()
    if not desktop or not desktop.is_dir():
        print("No pude detectar tu escritorio. Indícalo con: sb desktop --path <ruta>",
              file=sys.stderr)
        return 1

    registered = register_desktop_folders(_brain_dir(args), desktop)
    shortcut = create_shortcut(desktop, Path.cwd(), port=args.port)

    print(f"Escritorio: {desktop}")
    print(f"Acceso directo creado: {shortcut}")
    if registered:
        print(f"Carpetas conectadas como fuentes de SOLO lectura ({len(registered)}):")
        for entry in registered:
            print(f"  · {entry['alias']}")
    else:
        print("Tu escritorio no tiene subcarpetas; agrega fuentes con sb sources add.")
    print("\nSiguiente paso — primera sincronización (heurística, sin costo):")
    print("  sb sources sync --no-llm")
    print("Con extracción semántica de Claude: sb sources sync")
    return 0


def cmd_serve(args) -> int:
    from .server import serve
    if args.snapshot:
        from .snapshot import SnapshotStore
        store = SnapshotStore.from_file(args.snapshot)
    else:
        store = BrainStore(args.db)
    serve(store, host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sb", description="Segundo Cerebro — Personal Cognitive OS")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"ruta de la base (default: {DEFAULT_DB})")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="ingesta un archivo o directorio Markdown")
    p.add_argument("path")
    p.add_argument("--no-llm", action="store_true", help="usar solo extracción heurística")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("ask", help="pregunta al segundo cerebro")
    p.add_argument("question")
    p.add_argument("--context-only", action="store_true", help="mostrar solo el context pack")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("search", help="búsqueda directa en la memoria")
    p.add_argument("query")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("tasks", help="compromisos abiertos")
    p.add_argument("--status", default="active")
    p.set_defaults(func=lambda a: cmd_list(a, "task"))

    p = sub.add_parser("decisions", help="registro de decisiones")
    p.add_argument("--status", default=None)
    p.set_defaults(func=lambda a: cmd_list(a, "decision"))

    p = sub.add_parser("entities", help="entidades del knowledge graph")
    p.set_defaults(func=cmd_entities)

    p = sub.add_parser("timeline", help="memoria episódica (eventos)")
    p.set_defaults(func=cmd_timeline)

    so = sub.add_parser("sources", help="carpetas locales como fuentes (solo lectura)")
    ssub = so.add_subparsers(dest="sources_command", required=True)

    sp = ssub.add_parser("add", help="registra una carpeta")
    sp.add_argument("path")
    sp.add_argument("--alias")
    sp.set_defaults(func=cmd_sources_add)

    sp = ssub.add_parser("list", help="lista las fuentes registradas")
    sp.set_defaults(func=cmd_sources_list)

    sp = ssub.add_parser("remove", help="quita una carpeta del registro")
    sp.add_argument("path")
    sp.set_defaults(func=cmd_sources_remove)

    sp = ssub.add_parser("sync", help="sincroniza todas las fuentes a la memoria")
    sp.add_argument("--no-llm", action="store_true", help="extracción heurística")
    sp.set_defaults(func=cmd_sources_sync)

    p = sub.add_parser("desktop", help="acceso directo + carpetas del escritorio como fuentes")
    p.add_argument("--path", help="ruta del escritorio si la detección falla")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_desktop)

    p = sub.add_parser("export", help="exporta la memoria a un snapshot JSON (para desplegar)")
    p.add_argument("output", nargs="?", default="data/snapshot.json")
    p.add_argument("--no-bodies", action="store_true",
                   help="omite el texto completo de los documentos")
    p.set_defaults(func=cmd_export)

    g = sub.add_parser("google", help="conectores Google (Drive + Calendar, multi-cuenta)")
    gsub = g.add_subparsers(dest="google_command", required=True)

    gp = gsub.add_parser("connect", help="autoriza una cuenta Gmail (abre el navegador)")
    gp.add_argument("alias", help="nombre corto de la cuenta: personal, falp, …")
    gp.set_defaults(func=cmd_google_connect)

    gp = gsub.add_parser("accounts", help="lista cuentas conectadas")
    gp.set_defaults(func=cmd_google_accounts)

    gp = gsub.add_parser("sync", help="sincroniza Calendar y Drive a la memoria")
    gp.add_argument("--account", help="solo esta cuenta (default: todas)")
    gp.add_argument("--no-calendar", action="store_true")
    gp.add_argument("--no-drive", action="store_true")
    gp.add_argument("--days-back", type=int, default=30, help="eventos pasados (default 30)")
    gp.add_argument("--days-forward", type=int, default=30, help="eventos futuros (default 30)")
    gp.add_argument("--query", help="filtro extra de Drive, p. ej. \"name contains 'FALP'\"")
    gp.add_argument("--no-llm", action="store_true", help="extracción heurística")
    gp.set_defaults(func=cmd_google_sync)

    p = sub.add_parser("serve", help="UI web con el grafo de conocimiento")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--snapshot", help="servir un snapshot de solo lectura en vez de la base")
    p.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
