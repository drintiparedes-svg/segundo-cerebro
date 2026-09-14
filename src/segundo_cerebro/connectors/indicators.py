"""Indicadores económicos oficiales (UF, dólar, euro, IPC, UTM) vía
mindicador.cl (API pública que republica al Banco Central de Chile).
Caché local de 24 h en .brain/state/indicators.json."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .validated import get_json, now_iso

API = "https://mindicador.cl/api"
KEYS = ("uf", "dolar", "euro", "ipc", "utm", "tpm")
TTL_HOURS = 24


def fetch_indicators(fetch=None) -> dict:
    data = get_json(API, fetch)
    out = {"retrieved_at": now_iso(), "source": API, "values": {}}
    for k in KEYS:
        v = data.get(k)
        if isinstance(v, dict) and v.get("valor") is not None:
            out["values"][k] = {"value": float(v["valor"]), "unit": v.get("unidad_medida", ""),
                                "date": (v.get("fecha") or "")[:10], "name": v.get("nombre", k)}
    return out


def cache_path(brain_dir: str | Path) -> Path:
    d = Path(brain_dir) / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d / "indicators.json"


def load_cached(brain_dir: str | Path) -> dict | None:
    p = cache_path(brain_dir)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def get_indicators(brain_dir: str | Path, fetch=None, max_age_hours: int = TTL_HOURS,
                   offline: bool = False) -> dict:
    """Valores cacheados si son recientes; si no, consulta (salvo offline)."""
    cached = load_cached(brain_dir)
    if cached:
        try:
            age = datetime.utcnow() - datetime.strptime(cached["retrieved_at"], "%Y-%m-%dT%H:%M:%SZ")
            if age < timedelta(hours=max_age_hours) or offline:
                return cached
        except (KeyError, ValueError):
            pass
    if offline:
        return cached or {"values": {}, "retrieved_at": None, "source": API}
    try:
        data = fetch_indicators(fetch)
    except Exception as exc:
        if cached:
            return {**cached, "stale": True, "error": str(exc)}
        return {"values": {}, "retrieved_at": None, "source": API, "error": str(exc)}
    cache_path(brain_dir).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def clp_to_usd(amount_clp: float, indicators: dict) -> float | None:
    usd = (indicators.get("values") or {}).get("dolar", {}).get("value")
    return round(amount_clp / usd, 2) if usd else None


def clp_to_uf(amount_clp: float, indicators: dict) -> float | None:
    uf = (indicators.get("values") or {}).get("uf", {}).get("value")
    return round(amount_clp / uf, 2) if uf else None
