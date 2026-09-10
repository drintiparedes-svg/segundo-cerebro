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
    _auto_assign(args, store)
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
    _auto_assign(args, _store(args))
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
    _auto_assign(args, store)
    print(f"Total — documentos: {summary['documents']} · KOs: {summary['knowledge_objects']} · "
          f"entidades: {summary['entities']} · relaciones: {summary['relationships']}")
    return 0


def cmd_sources_suggest(args) -> int:
    """Asesor de carpetas: qué conectar, qué ignorar (solo nombres/fechas)."""
    from .advisor import apply_suggestion, candidate_roots, suggest_sources
    from .areas import load_areas
    from .desktop import find_desktop

    brain_dir = _brain_dir(args)
    roots = ([Path(r).expanduser() for r in args.root] if args.root
             else candidate_roots(find_desktop()))
    if not roots:
        print("No encontré escritorio ni carpetas estándar. Indica una: "
              "sb sources suggest --root <carpeta>", file=sys.stderr)
        return 1
    print("Raíces revisadas: " + ", ".join(str(r) for r in roots))
    suggestions = suggest_sources(brain_dir, roots, load_areas())
    if not suggestions:
        print("Nada nuevo que sugerir: todo está conectado o ignorado.")
        return 0
    icon = {"conectar": "✔", "revisar": "?", "ignorar": "–"}
    for s in suggestions:
        area = f" → {s['area_guess']}" if s["area_guess"] else ""
        print(f"{icon[s['verdict']]} {s['verdict']:<8} {s['name']}{area}  "
              f"[{s['files']} archivos, {s['recent']} recientes]")
        print(f"    {'; '.join(s['reasons'])}")
    if not args.apply:
        print("\nAplica con: sb sources suggest --apply  (una a una, Enter acepta "
              "las «conectar», n ignora, s salta, q termina)")
        return 0

    print("\nRevisión — Enter acepta la sugerencia · y conecta · n ignora · "
          "s salta · q termina")
    for s in suggestions:
        try:
            answer = input(f"{s['verdict']:<8} {s['name']} > ").strip().lower()
        except EOFError:
            break
        if answer == "q":
            break
        if answer == "s":
            continue
        accept = (answer == "y") or (answer == "" and s["verdict"] == "conectar")
        if answer == "" and s["verdict"] == "revisar":
            continue
        result = apply_suggestion(brain_dir, s["path"], accept)
        print(f"    {result['action']}")
    print("\nSincroniza lo nuevo con: sb sources sync --no-llm")
    return 0


def cmd_google_suggest(args) -> int:
    """Qué carpetas de Drive y calendarios seguir, por cuenta."""
    from .advisor import drive_query_suggestions
    from .areas import load_areas
    from .connectors.google_auth import list_accounts, load_state, save_state

    accounts = [args.account] if args.account else list_accounts()
    if not accounts:
        print("Sin cuentas conectadas. Usa: sb google connect <alias>", file=sys.stderr)
        return 1
    for alias in accounts:
        print(f"\n== Cuenta {alias} ==")
        state = load_state(alias)
        try:
            from .connectors.gcalendar import list_calendars
            cals = list_calendars(alias)
        except Exception as exc:
            print(f"  calendarios: no disponibles ({exc})")
            cals = []
        chosen_cals = set(state.get("calendars") or ["primary"])
        for i, c in enumerate(cals, 1):
            mark = "✔" if (c["id"] in chosen_cals or (c["primary"] and "primary" in chosen_cals)) else " "
            print(f"  [{mark}] {i}. {c['name']}{' (principal)' if c['primary'] else ''}")
        try:
            from .connectors.gdrive import list_root_folders
            folders = list_root_folders(alias)
        except Exception as exc:
            print(f"  carpetas Drive: no disponibles ({exc})")
            folders = []
        chosen_folders = {f["id"] for f in state.get("drive_folders", [])}
        for i, f in enumerate(folders, 1):
            mark = "✔" if f["id"] in chosen_folders else " "
            print(f"  [{mark}] D{i}. {f['name']}")
        if not args.apply:
            continue
        try:
            ans = input("  Calendarios a seguir (números separados por coma, "
                        "Enter mantiene): ").strip()
            if ans:
                idx = [int(x) for x in ans.replace(" ", "").split(",") if x]
                state["calendars"] = [cals[i - 1]["id"] for i in idx if 0 < i <= len(cals)]
            ans = input("  Carpetas de Drive a seguir (D-números, Enter = toda la "
                        "unidad): ").strip().lower().replace("d", "")
            if ans:
                idx = [int(x) for x in ans.replace(" ", "").split(",") if x]
                state["drive_folders"] = [{"id": folders[i - 1]["id"],
                                           "name": folders[i - 1]["name"]}
                                          for i in idx if 0 < i <= len(folders)]
                state.pop("drive_last_modified", None)  # re-barrer con el nuevo filtro
            save_state(alias, state)
            print("  guardado.")
        except (EOFError, ValueError):
            print("  sin cambios.")
    print("\nFiltros de Drive sugeridos por área (úsalos con sb google sync --query):")
    for s in drive_query_suggestions(load_areas()):
        print(f"  {s['area']:<14} {s['query']}")
    return 0


def cmd_people(args) -> int:
    from .people import people_scores, signals_label
    data = people_scores(_store(args), _brain_dir(args))
    if not data["people"]:
        print("Aún no hay personas en el grafo. Ingesta o sincroniza primero.")
        return 0
    print("Personas por relevancia (📌 = fijada por ti)\n")
    for r in data["people"][:25]:
        pin = "📌 " if r["pinned"] else "   "
        role = f" — {r['role']}" if r.get("role") else ""
        print(f"{pin}#{r['rank']:<3} {r['name']}{role}  (score {r['score']}: "
              f"{signals_label(r['signals'])})")
    if data["suggested"]:
        print("\nSugerencia: fija a " + ", ".join(data["suggested"])
              + "  →  sb people pin \"Nombre\" --role \"…\"")
    if data["unknown_senders"]:
        print("Remitentes frecuentes fuera del grafo: "
              + ", ".join(f"{u['name']} ({u['mails']})" for u in data["unknown_senders"]))
    return 0


def cmd_people_pin(args) -> int:
    from .people import set_person_override
    entry = set_person_override(_brain_dir(args), args.name, pin=not args.unpin,
                                role=args.role, area=args.area, note=args.note)
    print(f"{args.name}: {'fijada' if entry.get('pin') else 'sin pin'} {entry}")
    return 0


def cmd_refresh(args) -> int:
    from .refresh import run_refresh
    say = (lambda m: None) if args.quiet else print
    if not args.quiet:
        print("Actualizando el cerebro (todo local; Google solo lectura)…")
    state = run_refresh(_store(args), _brain_dir(args), skip=args.skip, log=say)
    if state.get("locked"):
        print("Ya hay un refresh en curso; no se duplica.", file=sys.stderr)
        return 0
    if not args.quiet:
        print(f"Listo en {state['duration_s']}s · {'sin errores' if state['ok'] else 'con errores (ver .brain/logs/)'}")
    return 0 if state["ok"] else 1


def cmd_schedule(args) -> int:
    from . import scheduler
    project_dir = Path.cwd()
    if args.schedule_command == "install":
        result = scheduler.install(project_dir, str(Path(args.db).resolve()),
                                   every=args.every, dry_run=args.dry_run)
        print(f"Plataforma: {result['platform']} · cada {result['minutes']} min"
              f"{' (simulación)' if args.dry_run else ' · instalado'}")
        if result["platform"] == "linux":
            print("crontab: " + result["cron_line"])
        elif result["platform"] == "macos":
            print("LaunchAgent: " + result["plist_path"])
        else:
            for cmd in result["commands"]:
                print("  " + " ".join(cmd))
        print("El servicio corre `sb refresh --quiet`: sincroniza, triaja y genera el "
              "brief. Estado: sb schedule status")
        return 0
    if args.schedule_command == "remove":
        result = scheduler.remove(dry_run=args.dry_run)
        print(f"{result['platform']}: {'eliminado' if result['removed'] else 'simulación'}")
        return 0
    result = scheduler.status()
    print(f"{result['platform']}: {'instalado' if result['installed'] else 'no instalado'}")
    if result.get("detail"):
        print(result["detail"])
    return 0


def cmd_enrich(args) -> int:
    from .enrich import enrich
    result = enrich(_store(args), _brain_dir(args), areas=args.area,
                    limit=args.limit, dry_run=args.dry_run)
    if result.get("skipped"):
        print(f"Omitido: {result['skipped']}")
        return 0
    if args.dry_run:
        print(f"Pendientes de enriquecer en {', '.join(result['areas'])}: {result['pending']}")
        for d in result["docs"][:20]:
            print(f"  [{d['area']}] {d['title']}")
        return 0
    print(f"Enriquecidos con {result['extractor']}: {result['enriched']} documentos "
          f"({', '.join(result['areas'])}) · KOs nuevos: {result['knowledge_objects']} "
          f"(reemplazaron {result['removed']['kos']} heurísticos)")
    return 0


def cmd_config(args) -> int:
    from .config import load_config, set_llm_areas
    brain_dir = _brain_dir(args)
    if args.config_command == "llm" and args.areas is not None:
        try:
            cfg = set_llm_areas(brain_dir, args.areas)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
        print("Claude habilitado en: " + (", ".join(cfg["llm"]["areas"]) or "ninguna"))
        return 0
    import json as _json
    print(_json.dumps(load_config(brain_dir), ensure_ascii=False, indent=2))
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


def cmd_organize(args) -> int:
    from .agents import save_report
    from .agents.curator import organize, to_markdown

    store = _store(args)
    collections = organize(store, prefer_llm=not args.no_llm)
    if not collections:
        print("La memoria está vacía; ingesta o sincroniza fuentes primero.")
        return 0
    report = to_markdown(collections, store)
    path = save_report(_brain_dir(args), "colecciones", report)
    for col in collections:
        print(f"{col['name']:32} {len(col['doc_ids']):4} docs · {col['rationale']}")
    print(f"\nInforme completo: {path}")
    return 0


def cmd_collections(args) -> int:
    store = _store(args)
    cols = store.list_collections()
    if not cols:
        print("Sin colecciones. Genera la agrupación con: sb agent organize")
        return 0
    for col in cols:
        print(f"{col['name']:32} {len(col['doc_ids']):4} docs")
    return 0


def cmd_mail_triage(args) -> int:
    from .agents import save_latest_triage, save_report
    from .agents.mail_triage import PRIORITIES, to_markdown, triage
    from .connectors.gmail import fetch_inbox, sender_name
    from .connectors.google_auth import GoogleAuthError, list_accounts

    accounts = [args.account] if args.account else list_accounts()
    if not accounts:
        print("Sin cuentas conectadas. Usa: sb google connect <alias>", file=sys.stderr)
        return 1

    emails = []
    for alias in accounts:
        try:
            emails.extend(fetch_inbox(
                alias, days=args.days, query=args.query,
                include_bodies=args.bodies, limit=args.limit))
        except GoogleAuthError as exc:
            print(exc, file=sys.stderr)
    if not emails:
        print("No hay correos en el período consultado.")
        return 0

    store = _store(args)
    triaged = triage(emails, store, prefer_llm=not args.no_llm)
    report = to_markdown(triaged)
    path = save_report(_brain_dir(args), "triaje-correo", report)
    save_latest_triage(_brain_dir(args), triaged)

    current = None
    for mail in triaged:
        if mail["priority"] != current:
            current = mail["priority"]
            print(f"\n{PRIORITIES[current]}")
        print(f"  {sender_name(mail.get('from', '?')):28.28} {mail.get('subject', '')[:60]}")
    print(f"\nInforme completo (local): {path}")
    print("Tu bandeja no fue modificada (scope de solo lectura).")
    return 0


def _auto_assign(args, store) -> None:
    """Re-clasifica por área tras cada ingesta/sync, si hay mapa de áreas.
    100% local (palabras clave); silencioso si no existe brain/self/areas.md."""
    from .areas import assign_all, load_areas
    areas = load_areas()
    if areas:
        assign_all(store, areas)


def cmd_areas(args) -> int:
    from .areas import load_areas
    from .priority import area_scores, signals_label
    areas = load_areas()
    if not areas:
        print("No existe brain/self/areas.md — crea tu mapa de áreas primero.",
              file=sys.stderr)
        return 1
    rows = area_scores(_store(args), areas, _brain_dir(args))
    print(f"{'#':>2} {'Área':32} {'score':>6} {'peso':>5}  señales")
    for r in rows:
        mark = f"📌{r['pin']}" if r["pin"] is not None else (
            "⏸" if r["status"] == "pausada" else "  ")
        print(f"{r['rank']:>2} {r['name']:32} {r['score']:>6} {r['weight']:>5} "
              f"{mark} {signals_label(r['signals'])}")
    print("\nAjustes: sb areas set <id> --weight W | --pin N | --pause · "
          "interactivo: sb areas review")
    return 0


def cmd_areas_set(args) -> int:
    from .priority import set_override
    entry = set_override(_brain_dir(args), args.id, weight=args.weight,
                         pin=args.pin, unpin=args.unpin,
                         status="pausada" if args.pause else
                                ("activa" if args.resume else None))
    print(f"{args.id}: {entry}")
    return cmd_areas(args)


def cmd_areas_review(args) -> int:
    from .areas import load_areas
    from .priority import area_scores, set_override, signals_label
    areas = load_areas()
    store = _store(args)
    brain_dir = _brain_dir(args)
    print("Revisión de prioridades — Enter acepta · w <n> ajusta peso · "
          "p <n> fija posición · x pausa · q termina\n")
    for r in area_scores(store, areas, brain_dir):
        prompt = (f"#{r['rank']} {r['name']} (score {r['score']}, "
                  f"{signals_label(r['signals'])}) > ")
        try:
            answer = input(prompt).strip().lower()
        except EOFError:
            break
        if answer == "q":
            break
        if answer == "x":
            set_override(brain_dir, r["id"], status="pausada")
        elif answer.startswith("w "):
            try:
                set_override(brain_dir, r["id"], weight=float(answer[2:]))
            except ValueError:
                print("  peso inválido, se mantiene")
        elif answer.startswith("p "):
            try:
                set_override(brain_dir, r["id"], pin=int(answer[2:]))
            except ValueError:
                print("  posición inválida, se mantiene")
    print("\nRanking validado:")
    return cmd_areas(args)


def cmd_areas_assign(args) -> int:
    from .areas import assign_all, load_areas
    areas = load_areas()
    if not areas:
        print("No existe brain/self/areas.md — crea tu mapa de áreas primero.",
              file=sys.stderr)
        return 1
    summary = assign_all(_store(args), areas)
    print(f"Documentos clasificados: {summary['documents']} "
          f"(sin área: {summary['unassigned']}) · KOs: {summary['kos']}")
    print("Clasificación 100% local (palabras clave + personas + proyectos).")
    return 0


def cmd_today(args) -> int:
    from .agents import save_report
    from .areas import load_areas
    from .today import build_today

    store = _store(args)
    brief = build_today(store, _brain_dir(args), load_areas())
    print(brief)
    if args.save:
        path = save_report(_brain_dir(args), "brief", brief)
        print(f"\nGuardado en {path}")
    return 0


def cmd_add(args) -> int:
    """Subida manual de archivos sueltos desde el notebook (solo lectura)."""
    import shutil
    from .connectors.localfs import file_to_document, read_file_text
    from .extract import get_extractor
    from .ingest import new_summary, process_document

    store = _store(args)
    extractor = get_extractor(prefer_llm=not args.no_llm)
    summary = new_summary(extractor)
    added = 0
    for raw in args.paths:
        path = Path(raw).expanduser()
        if not path.is_file():
            print(f"Omitido (no es archivo): {path}", file=sys.stderr)
            continue
        if args.copy:
            uploads = _brain_dir(args) / "uploads"
            uploads.mkdir(parents=True, exist_ok=True)
            copied = uploads / path.name
            shutil.copy2(path, copied)
            path = copied
        text = read_file_text(path)
        if text is None or not text.strip():
            print(f"Formato no soportado o vacío: {path}", file=sys.stderr)
            continue
        doc = file_to_document(path, "subida-manual", text)
        if args.area:
            doc.area = args.area
        if not store.add_document(doc):
            print(f"Ya estaba en la memoria: {path.name}")
            continue
        summary["documents"] += 1
        process_document(store, doc, extractor, summary)
        added += 1
        print(f"Agregado: {doc.title} → {path}")
    if not args.area:
        _auto_assign(args, store)
    print(f"Documentos nuevos: {added} · KOs: {summary['knowledge_objects']}")
    return 0 if added or not args.paths else 1


def cmd_zotero_import(args) -> int:
    from .connectors.zotero import import_library
    store = _store(args)
    try:
        docs = import_library(store, Path(args.file))
    except (FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    _auto_assign(args, store)
    for doc in docs[:20]:
        print(f"{doc.metadata.get('year', ''):>4} · {doc.title}")
    print(f"\nReferencias nuevas en la memoria: {len(docs)}")
    return 0


def cmd_chats_import(args) -> int:
    from .connectors.chats import import_export
    from .extract import HeuristicExtractor
    from .ingest import new_summary, process_document

    store = _store(args)
    try:
        docs = import_export(store, Path(args.file), alias=args.alias)
    except (FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    summary = new_summary(HeuristicExtractor())
    for doc in docs:
        summary["documents"] += 1
        process_document(store, doc, HeuristicExtractor(), summary)
    _auto_assign(args, store)
    print(f"Días de conversación importados: {len(docs)} · "
          f"KOs: {summary['knowledge_objects']}")
    print("Memoria local: el contenido de los chats no sale de tu equipo.")
    return 0


def cmd_literature_verify(args) -> int:
    from .agents import save_report
    from .connectors.literature import verify_document
    from .connectors.localfs import read_file_text

    path = Path(args.file).expanduser()
    text = read_file_text(path) if path.suffix.lower() not in ("", ".md") \
        else path.read_text(encoding="utf-8", errors="replace")
    if not text:
        print(f"No pude leer {path}", file=sys.stderr)
        return 1
    report, ok_count, total = verify_document(text, source_name=path.name)
    out = save_report(_brain_dir(args), "verificacion", report)
    print(report)
    print(f"\nInforme guardado en {out} (el documento original no se toca).")
    return 0 if ok_count == total else 2


def cmd_draft(args) -> int:
    from .agents.writer import draft, list_templates, save_draft

    if args.list:
        for kind in list_templates():
            print(kind)
        return 0
    if not args.kind or not args.topic:
        print("Uso: sb draft <tipo> --topic \"tema\"  (tipos: sb draft --list)",
              file=sys.stderr)
        return 1
    store = _store(args)
    try:
        markdown, mode = draft(store, args.kind, args.topic, area=args.area,
                               prefer_llm=not args.no_llm)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    path = save_draft(_brain_dir(args), args.kind, markdown)
    print(markdown)
    print(f"\n---\nBorrador ({'redactado con Claude' if mode == 'claude' else 'andamiaje local'}) "
          f"guardado en {path}")
    print("Revísalo y edítalo antes de usarlo: este agente nunca envía nada.")
    return 0


def cmd_literature(args) -> int:
    from .connectors.literature import sync
    from .extract import get_extractor
    from .ingest import new_summary, process_document

    store = _store(args)
    try:
        docs = sync(store, args.query, limit=args.max, open_only=args.open_only)
    except Exception as exc:
        print(f"Error consultando Europe PMC: {exc}", file=sys.stderr)
        return 1
    extractor = get_extractor(prefer_llm=not args.no_llm)
    summary = new_summary(extractor)
    for doc in docs:
        summary["documents"] += 1
        process_document(store, doc, extractor, summary)
    _auto_assign(args, store)
    for doc in docs:
        oa = "OA" if doc.metadata.get("open_access") else "  "
        print(f"[{oa}] {doc.metadata.get('year', '')} · {doc.title}")
    print(f"\nArtículos nuevos: {len(docs)} (deduplicados contra la memoria)")
    return 0


def cmd_why(args) -> int:
    from .agents import save_report
    from .areas import load_areas
    from .why import build_dossier, to_markdown

    store = _store(args)
    dossier = build_dossier(store, args.query)
    if dossier is None:
        print(f"No encontré una decisión que calce con «{args.query}». "
              "Revisa el registro con: sb decisions", file=sys.stderr)
        return 1
    names = {a.id: a.name for a in load_areas()}
    md = to_markdown(dossier, names)
    print(md)
    if args.save:
        path = save_report(_brain_dir(args), "por-que", md)
        print(f"\nGuardado en {path}")
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

    sp = ssub.add_parser("suggest", help="asesor: qué carpetas conectar o ignorar")
    sp.add_argument("--root", action="append", help="raíz a revisar (repetible)")
    sp.add_argument("--apply", action="store_true", help="aceptar/ignorar una a una")
    sp.set_defaults(func=cmd_sources_suggest)

    pe = sub.add_parser("people", help="personas clave: ranking y pin manual")
    pesub = pe.add_subparsers(dest="people_command")
    pe.set_defaults(func=cmd_people)
    pp = pesub.add_parser("pin", help="fija una persona como relevante")
    pp.add_argument("name")
    pp.add_argument("--role")
    pp.add_argument("--area")
    pp.add_argument("--note")
    pp.set_defaults(func=cmd_people_pin, unpin=False)
    pp = pesub.add_parser("unpin", help="suelta el pin de una persona")
    pp.add_argument("name")
    pp.set_defaults(func=cmd_people_pin, unpin=True, role=None, area=None, note=None)

    p = sub.add_parser("refresh", help="mantiene el cerebro al día: fuentes, Google, correo, áreas, brief")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--skip", action="append", help="omitir un paso (sources|google|mail|areas|enrich|brief)")
    p.set_defaults(func=cmd_refresh)

    sc = sub.add_parser("schedule", help="programa `sb refresh` en tu sistema (sin nube)")
    scsub = sc.add_subparsers(dest="schedule_command")
    sc.set_defaults(func=cmd_schedule, schedule_command="status")
    scp = scsub.add_parser("install", help="instala la tarea programada")
    scp.add_argument("--every", default="4h", help="intervalo: 4h, 90m (default 4h)")
    scp.add_argument("--dry-run", action="store_true", help="muestra sin instalar")
    scp.set_defaults(func=cmd_schedule)
    scp = scsub.add_parser("remove", help="quita la tarea programada")
    scp.add_argument("--dry-run", action="store_true")
    scp.set_defaults(func=cmd_schedule)
    scp = scsub.add_parser("status", help="¿está instalada?")
    scp.set_defaults(func=cmd_schedule)

    p = sub.add_parser("enrich", help="segunda pasada con Claude solo en las áreas habilitadas")
    p.add_argument("--area", action="append", help="limitar a un área (repetible)")
    p.add_argument("--limit", type=int)
    p.add_argument("--dry-run", action="store_true", help="lista lo pendiente sin llamar a Claude")
    p.set_defaults(func=cmd_enrich)

    cf = sub.add_parser("config", help="configuración local (.brain/config.json)")
    cfsub = cf.add_subparsers(dest="config_command")
    cf.set_defaults(func=cmd_config, config_command="show", areas=None)
    cfp = cfsub.add_parser("llm", help="áreas donde se permite Claude")
    cfp.add_argument("--areas", nargs="*", help="p. ej. academia falp (vacío = ninguna)")
    cfp.set_defaults(func=cmd_config)
    cfp = cfsub.add_parser("show", help="muestra la configuración")
    cfp.set_defaults(func=cmd_config, areas=None)

    p = sub.add_parser("desktop", help="acceso directo + carpetas del escritorio como fuentes")
    p.add_argument("--path", help="ruta del escritorio si la detección falla")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(func=cmd_desktop)

    ar = sub.add_parser("areas", help="áreas de trabajo: mapa y clasificación local")
    arsub = ar.add_subparsers(dest="areas_command")
    ar.set_defaults(func=cmd_areas)
    arp = arsub.add_parser("assign", help="re-clasifica toda la memoria por área")
    arp.set_defaults(func=cmd_areas_assign)

    arp = arsub.add_parser("set", help="validación manual: peso, pin o pausa de un área")
    arp.add_argument("id")
    arp.add_argument("--weight", type=float)
    arp.add_argument("--pin", type=int)
    arp.add_argument("--unpin", action="store_true")
    arp.add_argument("--pause", action="store_true")
    arp.add_argument("--resume", action="store_true")
    arp.set_defaults(func=cmd_areas_set)

    arp = arsub.add_parser("review", help="revisión interactiva del ranking")
    arp.set_defaults(func=cmd_areas_review)

    p = sub.add_parser("today", help="brief del día: agenda, compromisos, correo, preguntas")
    p.add_argument("--save", action="store_true", help="guardar en .brain/reports/")
    p.set_defaults(func=cmd_today)

    p = sub.add_parser("add", help="sube archivos sueltos del notebook a la memoria")
    p.add_argument("paths", nargs="+")
    p.add_argument("--area", help="forzar área")
    p.add_argument("--copy", action="store_true", help="copiar a .brain/uploads/")
    p.add_argument("--no-llm", action="store_true")
    p.set_defaults(func=cmd_add)

    z = sub.add_parser("zotero", help="biblioteca de referencias (BibTeX / CSL-JSON)")
    zsub = z.add_subparsers(dest="zotero_command", required=True)
    zp = zsub.add_parser("import", help="importa un export .bib o .json de Zotero")
    zp.add_argument("file")
    zp.set_defaults(func=cmd_zotero_import)

    ch = sub.add_parser("chats", help="exports de WhatsApp (.txt) o Slack (.zip)")
    chsub = ch.add_subparsers(dest="chats_command", required=True)
    cp = chsub.add_parser("import")
    cp.add_argument("file")
    cp.add_argument("--alias", help="nombre del chat/canal")
    cp.set_defaults(func=cmd_chats_import)

    p = sub.add_parser("draft", help="borrador de documento desde tu memoria (revisión humana siempre)")
    p.add_argument("kind", nargs="?", help="onepager | informe-academico | plan-trabajo | minuta | informe-gestion")
    p.add_argument("--topic", help="tema del documento")
    p.add_argument("--area", help="limitar el material a un área (id de areas.md)")
    p.add_argument("--list", action="store_true", help="lista las plantillas")
    p.add_argument("--no-llm", action="store_true", help="andamiaje 100% local")
    p.set_defaults(func=cmd_draft)

    p = sub.add_parser("literature", help="literatura: búsqueda abierta y validación de referencias")
    lsub = p.add_subparsers(dest="literature_command")
    lp = lsub.add_parser("search", help="busca en Europe PMC y guarda en la memoria")
    lp.add_argument("query")
    lp.add_argument("--max", type=int, default=15)
    lp.add_argument("--open-only", action="store_true")
    lp.add_argument("--no-llm", action="store_true")
    lp.set_defaults(func=cmd_literature)
    lp = lsub.add_parser("verify", help="valida las referencias de un documento (informe, no edita)")
    lp.add_argument("file")
    lp.set_defaults(func=cmd_literature_verify)
    lsub.required = True

    p = sub.add_parser("why", help="por qué se tomó una decisión: cadena, evidencia y pendientes")
    p.add_argument("query", help="tema o texto de la decisión")
    p.add_argument("--save", action="store_true", help="guardar en .brain/reports/")
    p.set_defaults(func=cmd_why)

    ag = sub.add_parser("agent", help="agentes: curador de archivos y triaje de correo")
    asub = ag.add_subparsers(dest="agent_command", required=True)

    ap = asub.add_parser("organize", help="agrupa todos los documentos en colecciones")
    ap.add_argument("--no-llm", action="store_true", help="modo 100% local")
    ap.set_defaults(func=cmd_organize)

    ap = asub.add_parser("mail", help="prioriza tu bandeja de Gmail (solo lectura)")
    ap.add_argument("--account", help="solo esta cuenta (default: todas)")
    ap.add_argument("--days", type=int, default=7, help="ventana en días (default 7)")
    ap.add_argument("--limit", type=int, default=50, help="máx. correos por cuenta")
    ap.add_argument("--query", help="filtro Gmail, p. ej. 'from:falp.org'")
    ap.add_argument("--bodies", action="store_true",
                    help="incluir cuerpo completo (por defecto solo asunto+snippet)")
    ap.add_argument("--no-llm", action="store_true",
                    help="modo 100% local: nada sale de tu máquina")
    ap.set_defaults(func=cmd_mail_triage)

    p = sub.add_parser("collections", help="colecciones generadas por el curador")
    p.set_defaults(func=cmd_collections)

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

    gp = gsub.add_parser("suggest", help="qué calendarios y carpetas de Drive seguir")
    gp.add_argument("--account", help="solo esta cuenta")
    gp.add_argument("--apply", action="store_true", help="elegir interactivamente")
    gp.set_defaults(func=cmd_google_suggest)

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
