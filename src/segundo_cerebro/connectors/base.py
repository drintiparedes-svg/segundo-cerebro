"""Connector SDK: el contrato común de toda fuente de información.

Una fuente es una *instancia* de un tipo de conector (`localfs`, `gdrive`,
`gcalendar`, `gmail`, `zotero`, `chats`, …) con su configuración y su
estado, registrada en `.brain/connectors.json`. El contrato:

    test()        ¿puedo llegar a la fuente?        → {"ok", "detail"}
    sync(store)   trae lo nuevo, idempotente        → SyncResult
    disconnect()  quita la instancia; con purga, borra lo que aportó

Cada documento lleva `connector_id` (la instancia que lo trajo) para que
desconectar pueda borrar exactamente lo suyo. Terceros agregan tipos con
`entry_points(group="segundo_cerebro.connectors")` que devuelvan una
subclase de `Connector`.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..models import Document, now_iso

STATE_FILE = "connectors.json"
KINDS = ("local", "cloud", "api")
PRIVACY = ("local", "read-cloud", "write-cloud")


@dataclass
class ConnectorSpec:
    id: str                      # tipo: localfs, gdrive, …
    name: str
    kind: str                    # local | cloud | api
    privacy: str                 # local | read-cloud | write-cloud
    description: str = ""
    multi: bool = True           # ¿varias instancias (carpetas, cuentas)?
    config_schema: dict = field(default_factory=dict)   # campo → {"help", "required", "type"}
    setup_hint: str = ""         # cómo se conecta si no basta con la config


@dataclass
class SyncResult:
    added: list = field(default_factory=list)   # Documents nuevos ya insertados
    unchanged: int = 0
    skipped: int = 0
    detail: str = ""
    error: str | None = None

    def summary(self) -> dict:
        out = {"added": len(self.added), "unchanged": self.unchanged,
               "skipped": self.skipped, "detail": self.detail}
        if self.error:
            out["error"] = self.error
        return out


class Connector:
    """Base de todo conector. Las subclases fijan `spec` e implementan
    `test` y `sync`; `disconnect` por defecto delega la purga al store."""

    spec: ConnectorSpec

    def __init__(self, instance: dict, brain_dir: Path):
        self.instance = instance
        self.config = instance.get("config", {})
        self.state = instance.setdefault("state", {})
        self.brain_dir = Path(brain_dir)

    @property
    def id(self) -> str:
        return self.instance["id"]

    @property
    def label(self) -> str:
        return self.config.get("alias") or self.config.get("account") or \
            self.config.get("path") or self.id

    def test(self) -> dict:
        return {"ok": True, "detail": "sin prueba específica"}

    def sync(self, store) -> SyncResult:
        raise NotImplementedError

    def disconnect(self, store, purge: bool = False) -> dict:
        removed = store.delete_by_connector(self.id) if purge else {"documents": 0}
        return {"id": self.id, "purged": purge, **removed}

    @classmethod
    def make_id(cls, key: str) -> str:
        return instance_id(cls.spec.id, key)


# ── ids ───────────────────────────────────────────────────────────────────

_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def slug(text: str, limit: int = 40) -> str:
    return _SLUG_RE.sub("-", (text or "").strip()).strip("-")[:limit] or "x"


def instance_id(conn_type: str, key: str) -> str:
    return f"{conn_type}:{slug(key)}"


def connector_id_for(doc: Document) -> str | None:
    """Instancia que produjo un documento, deducida de sus metadatos.
    Se usa para documentos anteriores al campo `connector_id` y para las
    importaciones manuales (`sb zotero import`, `sb add`, captura)."""
    meta = doc.metadata or {}
    src = meta.get("source")
    if src == "local-folder":
        alias = meta.get("source_alias") or ""
        if alias == "subida-manual":
            return "upload"
        if alias == "plan-de-trabajo":
            return "plan"
        return instance_id("localfs", alias)
    if src == "google-drive":
        return instance_id("gdrive", meta.get("account", ""))
    if src == "google-calendar":
        return instance_id("gcalendar", meta.get("account", ""))
    if src == "zotero":
        return "zotero:manual"
    if src in ("whatsapp", "slack"):
        return "chats:manual"
    if src == "europepmc":
        return "literature:europepmc"
    if src == "gmail-capture":
        return "captured"
    return None


# ── registro en disco (.brain/connectors.json) ────────────────────────────

def state_path(brain_dir: str | Path) -> Path:
    p = Path(brain_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p / STATE_FILE


def empty_registry() -> dict:
    return {"instances": [], "localfs_ignored": [], "suggested_at": None}


def load_registry_file(brain_dir: str | Path) -> dict:
    path = state_path(brain_dir)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("instances", [])
        data.setdefault("localfs_ignored", [])
        data.setdefault("suggested_at", None)
        return data
    return _migrate_sources_json(Path(brain_dir))


def save_registry_file(brain_dir: str | Path, data: dict) -> None:
    state_path(brain_dir).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _migrate_sources_json(brain_dir: Path) -> dict:
    """Primera apertura: convierte el antiguo sources.json en instancias
    localfs. El archivo viejo queda como sources.json.migrated."""
    data = empty_registry()
    old = brain_dir / "sources.json"
    if old.exists():
        try:
            legacy = json.loads(old.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            legacy = {}
        for s in legacy.get("sources", []):
            st = legacy.get("state", {}).get(s["path"], {})
            data["instances"].append(new_instance(
                "localfs", s.get("alias") or Path(s["path"]).name,
                {"path": s["path"], "alias": s.get("alias") or Path(s["path"]).name},
                added_at=s.get("added_at"), state=st,
                last_sync=st.get("last_sync")))
        data["localfs_ignored"] = legacy.get("ignored", [])
        data["suggested_at"] = legacy.get("suggested_at")
        save_registry_file(brain_dir, data)
        old.rename(old.with_suffix(".json.migrated"))
    return data


def new_instance(conn_type: str, key: str, config: dict, added_at: str | None = None,
                 state: dict | None = None, last_sync: str | None = None,
                 enabled: bool = True) -> dict:
    return {"id": instance_id(conn_type, key), "type": conn_type, "config": config,
            "enabled": enabled, "added_at": added_at or now_iso(),
            "state": state or {}, "last_sync": last_sync, "last_result": None}


def unique_id(data: dict, wanted: str, config: dict) -> str:
    """Evita colisiones (dos carpetas «Proyectos»): sufijo por ruta."""
    taken = {i["id"]: i for i in data["instances"]}
    if wanted not in taken or taken[wanted].get("config") == config:
        return wanted
    digest = hashlib.sha1(json.dumps(config, sort_keys=True).encode()).hexdigest()[:6]
    return f"{wanted}-{digest}"
