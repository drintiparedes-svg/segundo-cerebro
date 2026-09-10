"""Configuración local del cerebro (.brain/config.json).

Un solo archivo, editable a mano, con los valores por defecto aplicados
al cargar. Aquí vive la política de extracción por área: heurística local
para todo y Claude solo en las áreas que el usuario marque. `clinica` está
en `never` por defecto y no se activa desde la UI (línea roja clínica).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

DEFAULTS: dict = {
    "refresh": {"every_hours": 4, "triage_days": 7, "days_back": 30,
                "days_forward": 30},
    "llm": {"default": "local", "areas": [], "never": ["clinica"],
            "max_docs_per_run": 40},
    "advisor": {"recent_days": 90, "max_files_per_folder": 5000,
                "max_depth": 4},
}


def config_path(brain_dir: str | Path) -> Path:
    return Path(brain_dir) / "config.json"


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(brain_dir: str | Path) -> dict:
    path = config_path(brain_dir)
    if path.exists():
        try:
            return _merge(DEFAULTS, json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return copy.deepcopy(DEFAULTS)


def save_config(brain_dir: str | Path, cfg: dict) -> Path:
    path = config_path(brain_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def llm_areas(cfg: dict) -> list[str]:
    """Áreas donde se permite la extracción con Claude: las marcadas menos
    las prohibidas (siempre gana `never`)."""
    never = set(cfg["llm"].get("never", []))
    return [a for a in cfg["llm"].get("areas", []) if a not in never]


def set_llm_areas(brain_dir: str | Path, areas: list[str]) -> dict:
    cfg = load_config(brain_dir)
    never = set(cfg["llm"].get("never", []))
    blocked = [a for a in areas if a in never]
    if blocked:
        raise ValueError(f"área(s) prohibida(s) para Claude: {', '.join(blocked)}")
    cfg["llm"]["areas"] = sorted(set(areas))
    save_config(brain_dir, cfg)
    return cfg
