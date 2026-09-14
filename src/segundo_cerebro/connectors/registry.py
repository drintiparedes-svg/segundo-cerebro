"""Registro de conectores: tipos disponibles, instancias configuradas y la
orquestación de sincronización/desconexión.

Tipos incorporados envuelven los módulos existentes (localfs, gdrive,
gcalendar, gmail, zotero, chats) sin reescribirlos. Las cuentas Google
autorizadas (`sb google connect`) se descubren solas como instancias.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from pathlib import Path

from .base import (Connector, ConnectorSpec, SyncResult, load_registry_file,
                   new_instance, save_registry_file, unique_id)


# ── tipos incorporados ────────────────────────────────────────────────────

class LocalFolderConnector(Connector):
    spec = ConnectorSpec(
        id="localfs", name="Carpeta local", kind="local", privacy="local",
        description="Carpeta de tu equipo, solo lectura (md, txt, pdf, docx, xlsx, pptx, csv, vtt).",
        config_schema={"path": {"type": "path", "required": True, "help": "ruta de la carpeta"},
                       "alias": {"type": "str", "required": False, "help": "nombre corto"}},
        setup_hint="sb connect add localfs --path <carpeta>  ·  o el asesor: sb sources suggest")

    def test(self) -> dict:
        p = Path(self.config.get("path", ""))
        return {"ok": p.is_dir(), "detail": str(p) if p.is_dir() else f"carpeta no disponible: {p}"}

    def sync(self, store) -> SyncResult:
        from .localfs import sync_source
        source = {"path": self.config["path"], "alias": self.config.get("alias") or Path(self.config["path"]).name}
        r = sync_source(store, self.brain_dir, source, state=self.state)
        if "error" in r:
            return SyncResult(error=r["error"])
        return SyncResult(added=r["docs"], unchanged=r["unchanged"], skipped=r["unsupported"])


class _GoogleConnector(Connector):
    api: tuple[str, str] = ("drive", "v3")

    @property
    def alias(self) -> str:
        return self.config.get("account", "")

    @property
    def base(self) -> Path:
        return self.brain_dir / "google"

    def test(self) -> dict:
        from .google_auth import build_service
        try:
            service = build_service(self.api[0], self.api[1], self.alias, base=self.base)
            if self.api[0] == "drive":
                service.about().get(fields="user").execute()
            elif self.api[0] == "calendar":
                service.calendarList().list(maxResults=1).execute()
            else:
                service.users().getProfile(userId="me").execute()
            return {"ok": True, "detail": f"cuenta «{self.alias}» accesible"}
        except Exception as exc:
            return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


class GoogleDriveConnector(_GoogleConnector):
    api = ("drive", "v3")
    spec = ConnectorSpec(
        id="gdrive", name="Google Drive", kind="cloud", privacy="read-cloud",
        description="Docs, Sheets, Slides, Word/Excel/PowerPoint y PDF de una cuenta (solo lectura).",
        config_schema={"account": {"type": "str", "required": True, "help": "alias de la cuenta"}},
        setup_hint="sb google connect <alias>  (OAuth de solo lectura)  ·  carpetas: sb google suggest")

    def sync(self, store) -> SyncResult:
        from . import gdrive
        added = gdrive.sync(store, self.alias, base=self.base)
        return SyncResult(added=added)


class GoogleCalendarConnector(_GoogleConnector):
    api = ("calendar", "v3")
    spec = ConnectorSpec(
        id="gcalendar", name="Google Calendar", kind="cloud", privacy="read-cloud",
        description="Eventos ±30 días de los calendarios elegidos (solo lectura).",
        config_schema={"account": {"type": "str", "required": True, "help": "alias de la cuenta"}},
        setup_hint="sb google connect <alias>  ·  calendarios: sb google suggest")

    def sync(self, store) -> SyncResult:
        from ..config import load_config
        from . import gcalendar
        r = load_config(self.brain_dir)["refresh"]
        added = gcalendar.sync(store, self.alias, r["days_back"], r["days_forward"], base=self.base)
        return SyncResult(added=added)


class GmailTriageConnector(_GoogleConnector):
    api = ("gmail", "v1")
    spec = ConnectorSpec(
        id="gmail", name="Gmail (triaje)", kind="cloud", privacy="read-cloud",
        description="Prioriza tu bandeja con metadatos; nunca guarda correos. Captura manual uno a uno.",
        config_schema={"account": {"type": "str", "required": True, "help": "alias de la cuenta"}},
        setup_hint="sb google connect <alias>  ·  triaje: sb agent mail  ·  captura: sb mail capture <id>")

    def sync(self, store) -> SyncResult:
        return SyncResult(detail="el triaje corre en el paso «mail» de sb refresh (sin persistir correos)")


class _FileImportConnector(Connector):
    importer = None   # (store, path, config) → list[Document]

    def test(self) -> dict:
        p = Path(self.config.get("path", ""))
        return {"ok": p.is_file(), "detail": str(p) if p.is_file() else f"archivo no disponible: {p}"}

    def sync(self, store) -> SyncResult:
        p = Path(self.config["path"])
        if not p.is_file():
            return SyncResult(error=f"archivo no disponible: {p}")
        mtime = p.stat().st_mtime
        if self.state.get("mtime") == mtime:
            return SyncResult(unchanged=1, detail="sin cambios desde la última importación")
        added = type(self).importer(store, p, self.config)
        self.state["mtime"] = mtime
        return SyncResult(added=added)


class ZoteroConnector(_FileImportConnector):
    spec = ConnectorSpec(
        id="zotero", name="Zotero / BibTeX", kind="local", privacy="local",
        description="Tu biblioteca exportada (.bib o CSL-JSON) como papers en la memoria.",
        config_schema={"path": {"type": "path", "required": True, "help": "export .bib o .json"}},
        setup_hint="sb connect add zotero --path biblioteca.bib")

    @staticmethod
    def importer(store, path, config):
        from .zotero import import_library
        return import_library(store, path)


class ChatsConnector(_FileImportConnector):
    spec = ConnectorSpec(
        id="chats", name="WhatsApp / Slack", kind="local", privacy="local",
        description="Export .txt de WhatsApp o .zip de Slack, un documento por día.",
        config_schema={"path": {"type": "path", "required": True, "help": "export .txt o .zip"},
                       "alias": {"type": "str", "required": False, "help": "nombre del chat"}},
        setup_hint="sb connect add chats --path export.txt --alias «Equipo datos»")

    @staticmethod
    def importer(store, path, config):
        from .chats import import_export
        return import_export(store, path, alias=config.get("alias"))


BUILTIN: dict[str, type[Connector]] = {
    c.spec.id: c for c in (LocalFolderConnector, GoogleDriveConnector, GoogleCalendarConnector,
                           GmailTriageConnector, ZoteroConnector, ChatsConnector)
}
GOOGLE_TYPES = ("gdrive", "gcalendar", "gmail")


def connector_types() -> dict[str, type[Connector]]:
    """Incorporados + plugins externos (entry point `segundo_cerebro.connectors`)."""
    types = dict(BUILTIN)
    try:
        for ep in entry_points(group="segundo_cerebro.connectors"):
            try:
                cls = ep.load()
                if isinstance(cls, type) and issubclass(cls, Connector) and getattr(cls, "spec", None):
                    types[cls.spec.id] = cls
            except Exception:
                continue   # un plugin roto no tumba el registro
    except Exception:
        pass
    return types


def register_type(cls: type[Connector]) -> None:
    """Registro en proceso (tests, extensiones embebidas)."""
    BUILTIN[cls.spec.id] = cls


# ── instancias ────────────────────────────────────────────────────────────

def load_instances(brain_dir: str | Path, discover_google: bool = True) -> dict:
    data = load_registry_file(brain_dir)
    if discover_google:
        _discover_google(Path(brain_dir), data)
    return data


def _discover_google(brain_dir: Path, data: dict) -> None:
    """Cada cuenta autorizada aparece como instancia gdrive/gcalendar/gmail
    (salvo que el usuario la haya desconectado: queda enabled=false)."""
    from .google_auth import list_accounts
    google_dir = brain_dir / "google"
    if not google_dir.is_dir():
        return
    known = {i["id"] for i in data["instances"]}
    changed = False
    for alias in list_accounts(google_dir):
        for t in GOOGLE_TYPES:
            inst = new_instance(t, alias, {"account": alias})
            if inst["id"] not in known:
                data["instances"].append(inst)
                known.add(inst["id"])
                changed = True
    if changed:
        save_registry_file(brain_dir, data)


def get_instance(brain_dir: str | Path, inst_id: str) -> dict | None:
    return next((i for i in load_instances(brain_dir)["instances"] if i["id"] == inst_id), None)


def build(brain_dir: str | Path, instance: dict) -> Connector:
    cls = connector_types().get(instance["type"])
    if cls is None:
        raise KeyError(f"tipo de conector desconocido: {instance['type']}")
    return cls(instance, Path(brain_dir))


def add_instance(brain_dir: str | Path, conn_type: str, config: dict,
                 key: str | None = None) -> dict:
    types = connector_types()
    if conn_type not in types:
        raise KeyError(f"tipo de conector desconocido: {conn_type} "
                       f"(disponibles: {', '.join(sorted(types))})")
    spec = types[conn_type].spec
    missing = [f for f, s in spec.config_schema.items() if s.get("required") and not config.get(f)]
    if missing:
        raise ValueError(f"faltan campos: {', '.join(missing)}")
    if "path" in config:
        config["path"] = str(Path(config["path"]).expanduser().resolve())
    if conn_type == "localfs":
        config.setdefault("alias", Path(config["path"]).name)
    data = load_instances(brain_dir)
    for i in data["instances"]:
        if i["type"] == conn_type and i["config"] == config:
            if not i.get("enabled", True):
                i["enabled"] = True
                save_registry_file(brain_dir, data)
            return i
    key = key or config.get("alias") or config.get("account") or Path(config.get("path", conn_type)).stem
    inst = new_instance(conn_type, key, config)
    inst["id"] = unique_id(data, inst["id"], config)
    data["instances"].append(inst)
    save_registry_file(brain_dir, data)
    return inst


def remove_instance(brain_dir: str | Path, store, inst_id: str, purge: bool = False,
                    forget: bool = False) -> dict:
    """Desconecta. Google: queda deshabilitada (el token sigue salvo
    `forget`); el resto se borra del registro. Con `purge`, borra de la
    memoria todo lo que aportó esa instancia."""
    data = load_instances(brain_dir)
    inst = next((i for i in data["instances"] if i["id"] == inst_id), None)
    if inst is None:
        raise KeyError(f"no existe la instancia {inst_id}")
    result = build(brain_dir, inst).disconnect(store, purge=purge)
    if inst["type"] in GOOGLE_TYPES:
        inst["enabled"] = False
        inst["state"] = {}
        if forget:
            alias = inst["config"].get("account")
            others = [i for i in data["instances"] if i["type"] in GOOGLE_TYPES
                      and i["config"].get("account") == alias and i["id"] != inst_id
                      and i.get("enabled", True)]
            if not others:
                token = Path(brain_dir) / "google" / f"token-{alias}.json"
                token.unlink(missing_ok=True)
                result["token_forgotten"] = True
    else:
        data["instances"] = [i for i in data["instances"] if i["id"] != inst_id]
    save_registry_file(brain_dir, data)
    return result


def test_instance(brain_dir: str | Path, inst_id: str) -> dict:
    inst = get_instance(brain_dir, inst_id)
    if inst is None:
        return {"ok": False, "detail": f"no existe la instancia {inst_id}"}
    try:
        return build(brain_dir, inst).test()
    except Exception as exc:
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


def sync_instances(store, brain_dir: str | Path, only: list[str] | None = None,
                   extractor=None) -> dict:
    """Sincroniza las instancias habilitadas (o `only`), corre la capa
    cognitiva local sobre lo nuevo y guarda estado por instancia."""
    from ..extract import HeuristicExtractor
    from ..ingest import new_summary, process_document
    from ..models import now_iso
    extractor = extractor or HeuristicExtractor()
    summary = new_summary(extractor)
    summary["instances"] = {}
    data = load_instances(brain_dir)
    for inst in data["instances"]:
        if not inst.get("enabled", True) or inst["type"] == "gmail":
            continue
        if only and inst["id"] not in only:
            continue
        try:
            conn = build(brain_dir, inst)
            result = conn.sync(store)
        except Exception as exc:
            result = SyncResult(error=f"{type(exc).__name__}: {exc}")
        for doc in result.added:
            store.set_connector(doc.id, inst["id"])
            summary["documents"] += 1
            process_document(store, doc, extractor, summary)
        inst["last_result"] = result.summary()
        if not result.error:
            inst["last_sync"] = now_iso()
        summary["instances"][inst["id"]] = inst["last_result"]
    save_registry_file(brain_dir, data)
    return summary


def describe(store, brain_dir: str | Path) -> list[dict]:
    """Instancias con su tipo, privacidad, estado y documentos aportados."""
    types = connector_types()
    counts = store.count_by_connector() if store is not None else {}
    out = []
    for inst in load_instances(brain_dir)["instances"]:
        cls = types.get(inst["type"])
        spec = cls.spec if cls else None
        conn = build(brain_dir, inst) if cls else None
        out.append({
            "id": inst["id"], "type": inst["type"],
            "type_name": spec.name if spec else inst["type"],
            "kind": spec.kind if spec else "?", "privacy": spec.privacy if spec else "?",
            "label": conn.label if conn else inst["id"], "config": inst["config"],
            "enabled": inst.get("enabled", True), "added_at": inst.get("added_at"),
            "last_sync": inst.get("last_sync"), "last_result": inst.get("last_result"),
            "documents": counts.get(inst["id"], 0),
        })
    return out


def types_payload() -> list[dict]:
    return [{"id": s.id, "name": s.name, "kind": s.kind, "privacy": s.privacy,
             "description": s.description, "multi": s.multi,
             "config_schema": s.config_schema, "setup_hint": s.setup_hint}
            for s in (c.spec for c in connector_types().values())]
