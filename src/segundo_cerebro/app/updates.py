"""Aviso de actualización opt-in: consulta GitHub Releases solo cuando tú
lo pides (`sb update-check`). Sin telemetría: la única información que
viaja es la petición pública a la API de GitHub."""

from __future__ import annotations

import json
import re

from .. import __version__

REPO = "drintiparedes-svg/segundo-cerebro"
API = f"https://api.github.com/repos/{REPO}/releases/latest"


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def check_latest(fetch=None) -> dict:
    from ..connectors.validated import get_json
    try:
        data = get_json(API, fetch)
    except Exception as exc:
        return {"current": __version__, "latest": None, "update": False, "error": str(exc)}
    tag = str(data.get("tag_name") or "").lstrip("v")
    return {"current": __version__, "latest": tag or None,
            "update": bool(tag) and _version_tuple(tag) > _version_tuple(__version__),
            "url": data.get("html_url"), "notes": (data.get("body") or "")[:600]}
