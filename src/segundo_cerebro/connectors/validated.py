"""Utilidades comunes de las fuentes validadas (técnicas y financieras).

Todas las consultas salen SOLO con los términos que tú eliges; cada
documento que entra lleva procedencia: `validated: true`, identificador
(PMID, DOI, NCT, URL) y `retrieved_at`. `fetch` es inyectable para probar
sin red.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

USER_AGENT = "segundo-cerebro/1.0 (personal cognitive OS; local use)"
TIMEOUT = 20


def http_get(url: str, headers: dict | None = None, timeout: int = TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def get_json(url: str, fetch=None) -> dict:
    raw = (fetch or http_get)(url)
    return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)


def get_text(url: str, fetch=None) -> str:
    raw = (fetch or http_get)(url)
    return raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)


def qs(**params) -> str:
    return urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def provenance(source: str, **ids) -> dict:
    return {"source": source, "validated": True, "retrieved_at": now_iso(),
            **{k: v for k, v in ids.items() if v}}
