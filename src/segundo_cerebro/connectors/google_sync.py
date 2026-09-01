"""Orquestación de sincronización Google (todas las cuentas conectadas).

`sync_all` recorre cada cuenta autorizada y cada servicio (Calendar, Drive),
inserta los documentos nuevos y corre la capa cognitiva sobre ellos, dejando
la memoria lista para el router y el context engine.
"""

from __future__ import annotations

from ..extract import get_extractor
from ..ingest import new_summary, process_document
from ..store import BrainStore
from . import gcalendar, gdrive
from .google_auth import list_accounts


def sync_all(store: BrainStore,
             accounts: list[str] | None = None,
             calendar: bool = True,
             drive: bool = True,
             days_back: int = 30,
             days_forward: int = 30,
             drive_query: str | None = None,
             prefer_llm: bool = True,
             base=None) -> dict:
    aliases = accounts or list_accounts(base)
    extractor = get_extractor(prefer_llm=prefer_llm)
    summary = new_summary(extractor)
    summary["accounts"] = {}

    for alias in aliases:
        added = []
        per_account = {"calendar": 0, "drive": 0, "errors": []}
        if calendar:
            try:
                docs = gcalendar.sync(store, alias, days_back, days_forward, base=base)
                per_account["calendar"] = len(docs)
                added.extend(docs)
            except Exception as exc:
                per_account["errors"].append(f"calendar: {exc}")
        if drive:
            try:
                docs = gdrive.sync(store, alias, query=drive_query, base=base)
                per_account["drive"] = len(docs)
                added.extend(docs)
            except Exception as exc:
                per_account["errors"].append(f"drive: {exc}")

        for doc in added:
            summary["documents"] += 1
            process_document(store, doc, extractor, summary)
        summary["accounts"][alias] = per_account

    return summary
