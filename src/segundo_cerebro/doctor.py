"""`sb doctor`: ¿está todo en su sitio? Dependencias, carpeta del cerebro,
configuración, conectores locales, Google, tarea programada, IA y última
sincronización. Solo lectura; devuelve una lista de comprobaciones con
nivel ok / warn / fail y cómo arreglar cada una."""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

from . import __version__

DEPS = [
    ("yaml", "pyyaml", "requerido", "pip install -e ."),
    ("openpyxl", "openpyxl", "Excel (planes, presupuestos)", "pip install -e '.[files]'"),
    ("docx", "python-docx", "Word", "pip install -e '.[files]'"),
    ("pptx", "python-pptx", "PowerPoint", "pip install -e '.[files]'"),
    ("pypdf", "pypdf", "PDF", "pip install -e '.[files]'"),
    ("googleapiclient", "google-api-python-client", "Drive/Calendar/Gmail", "pip install -e '.[google]'"),
    ("anthropic", "anthropic", "Claude (opcional)", "pip install -e '.[llm]'"),
    ("webview", "pywebview", "ventana de escritorio (opcional)", "pip install -e '.[app]'"),
]


def _check(cid: str, level: str, detail: str, fix: str = "") -> dict:
    return {"id": cid, "level": level, "ok": level == "ok", "detail": detail, "fix": fix}


def run_doctor(brain_dir: str | Path, store=None, test_connectors: bool = True) -> dict:
    brain_dir = Path(brain_dir)
    checks = []
    py = sys.version_info
    checks.append(_check("python", "ok" if py >= (3, 11) else "fail", f"Python {py.major}.{py.minor}.{py.micro}",
                         "" if py >= (3, 11) else "instala Python 3.11 o superior"))
    for mod, pkg, what, fix in DEPS:
        try:
            present = importlib.util.find_spec(mod) is not None
        except (ImportError, ValueError):
            present = False
        if present:
            checks.append(_check(f"dep:{pkg}", "ok", f"{pkg} — {what}"))
        else:
            checks.append(_check(f"dep:{pkg}", "fail" if pkg == "pyyaml" else "warn", f"{pkg} no instalado — {what}", fix))

    try:
        brain_dir.mkdir(parents=True, exist_ok=True)
        probe = brain_dir / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks.append(_check("brain_dir", "ok", f"{brain_dir} (escribible)"))
    except OSError as exc:
        checks.append(_check("brain_dir", "fail", f"{brain_dir}: {exc}", "elige otra carpeta con --db"))

    cfg_path = brain_dir / "config.json"
    if cfg_path.exists():
        try:
            json.loads(cfg_path.read_text(encoding="utf-8"))
            checks.append(_check("config", "ok", str(cfg_path)))
        except json.JSONDecodeError as exc:
            checks.append(_check("config", "fail", f"config.json inválido: {exc}", "corrige el JSON o bórralo (se regenera)"))
    else:
        checks.append(_check("config", "ok", "config.json aún no existe (se crea con valores por defecto)"))

    for name, hint in (("areas.md", "define tus áreas (docs/11)"), ("projects.md", "define tus proyectos (docs/15)")):
        p = Path("brain/self") / name
        checks.append(_check(f"seed:{name}", "ok" if p.exists() else "warn",
                             f"brain/self/{name} {'presente' if p.exists() else 'ausente'}", "" if p.exists() else hint))

    if store is not None:
        try:
            n = store.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            k = store.conn.execute("SELECT COUNT(*) FROM knowledge_objects").fetchone()[0]
            checks.append(_check("memory", "ok" if n else "warn", f"{n} documentos · {k} knowledge objects",
                                 "" if n else "conecta una carpeta: sb sources suggest --apply"))
        except Exception as exc:
            checks.append(_check("memory", "fail", f"base no accesible: {exc}", "revisa --db"))

    try:
        from .connectors import registry
        insts = registry.load_instances(brain_dir)["instances"]
        enabled = [i for i in insts if i.get("enabled", True)]
        checks.append(_check("connectors", "ok" if enabled else "warn", f"{len(enabled)} conectores habilitados",
                             "" if enabled else "sb connect add localfs --path <carpeta>"))
        if test_connectors:
            for i in enabled:
                if i["type"] in ("localfs", "zotero", "chats"):
                    r = registry.test_instance(brain_dir, i["id"])
                    checks.append(_check(f"connector:{i['id']}", "ok" if r["ok"] else "warn", r["detail"],
                                         "" if r["ok"] else f"sb connect remove {i['id']} si ya no existe"))
    except Exception as exc:
        checks.append(_check("connectors", "fail", f"registro ilegible: {exc}", "revisa .brain/connectors.json"))

    gdir = brain_dir / "google"
    secret = gdir / "client_secret.json"
    tokens = sorted(gdir.glob("token-*.json")) if gdir.is_dir() else []
    if tokens:
        from .connectors.google_auth import has_write_scope
        aliases = [t.stem.removeprefix("token-") for t in tokens]
        writes = [a for a in aliases if has_write_scope(a, gdir)]
        checks.append(_check("google", "ok", f"cuentas: {', '.join(aliases)}"
                             + (f" · escritura: {', '.join(writes)}" if writes else " · solo lectura")))
    else:
        checks.append(_check("google", "warn", "sin cuentas Google" + ("" if secret.exists() else " (falta client_secret.json)"),
                             "docs/07 → sb google connect <alias>"))

    try:
        from . import scheduler
        st = scheduler.status()
        checks.append(_check("schedule", "ok" if st["installed"] else "warn",
                             "tarea programada instalada" if st["installed"] else "sin tarea programada",
                             "" if st["installed"] else "sb schedule install --every 4h"))
    except Exception as exc:
        checks.append(_check("schedule", "warn", f"no pude consultar el programador: {exc}"))

    from .ai import status as ai_status
    ai = ai_status(brain_dir)
    checks.append(_check("ai", "ok" if ai["enabled"] else "warn",
                         "IA activa" if ai["enabled"] else f"IA apagada (modo manual supervisado, {ai.get('off_at') or '?'})",
                         "" if ai["enabled"] else "sb ai on cuando quieras reactivarla"))

    from .refresh import last_refresh
    last = last_refresh(brain_dir)
    if last and last.get("finished"):
        age_h = (datetime.now() - datetime.fromisoformat(last["finished"])).total_seconds() / 3600
        checks.append(_check("refresh", "ok" if age_h < 24 else "warn",
                             f"última sincronización hace {age_h:.1f} h" + ("" if last.get("ok") else " (con errores)"),
                             "" if age_h < 24 else "sb refresh"))
    else:
        checks.append(_check("refresh", "warn", "nunca sincronizado", "sb refresh"))

    summary = {"ok": sum(1 for c in checks if c["level"] == "ok"),
               "warn": sum(1 for c in checks if c["level"] == "warn"),
               "fail": sum(1 for c in checks if c["level"] == "fail")}
    return {"version": __version__, "checks": checks, "summary": summary, "healthy": summary["fail"] == 0}


def setup_status(brain_dir: str | Path, store=None) -> dict:
    """Primeros pasos: qué falta para que el cerebro trabaje solo."""
    brain_dir = Path(brain_dir)
    from .config import load_config, llm_areas
    from .connectors import registry
    from .people import pinned_names
    from . import scheduler
    from .ai import is_off
    insts = [i for i in registry.load_instances(brain_dir)["instances"] if i.get("enabled", True)]
    n_docs = 0
    if store is not None:
        try:
            n_docs = store.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        except Exception:
            n_docs = 0
    try:
        sched = scheduler.status()["installed"]
    except Exception:
        sched = False
    cfg = load_config(brain_dir)
    steps = [
        {"id": "sources", "title": "Conectar tus carpetas", "done": any(i["type"] == "localfs" for i in insts),
         "hint": "asesor en Conectores o sb sources suggest --apply", "tab": "sources"},
        {"id": "memory", "title": "Primera sincronización", "done": n_docs > 0,
         "hint": "Actualizar ahora o sb refresh", "tab": "today"},
        {"id": "google", "title": "Cuentas Google (Drive, Calendar, Gmail)", "done": any(i["type"] in ("gdrive", "gcalendar", "gmail") for i in insts),
         "hint": "sb google connect <alias> (docs/07)", "tab": "sources"},
        {"id": "people", "title": "Fijar personas clave", "done": bool(pinned_names(brain_dir)),
         "hint": "pestaña Personas", "tab": "people"},
        {"id": "llm", "title": "Decidir dónde usar Claude", "done": bool(llm_areas(cfg)) or is_off(brain_dir) or bool(cfg["llm"].get("areas")),
         "hint": "casillas por área en Conectores (o dejarlo apagado)", "tab": "sources"},
        {"id": "schedule", "title": "Programar la sincronización", "done": sched,
         "hint": "sb schedule install --every 4h", "tab": "today"},
    ]
    return {"steps": steps, "done": sum(1 for s in steps if s["done"]), "total": len(steps),
            "complete": all(s["done"] for s in steps)}
