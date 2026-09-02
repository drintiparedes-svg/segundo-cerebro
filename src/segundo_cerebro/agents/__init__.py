"""Capa de agentes (inicio del V4 del roadmap).

Principios no negociables (docs/10-agentes-y-privacidad.md):
- Los agentes LEEN y RECOMIENDAN; nunca ejecutan acciones externas.
- Todo informe se guarda solo en .brain/reports/ (local, fuera de git).
- Cada agente tiene un modo 100% local (--no-llm) en el que ningún dato
  sale de la máquina.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def save_report(brain_dir: str | Path, kind: str, markdown: str) -> Path:
    reports = Path(brain_dir) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    path = reports / f"{kind}-{stamp}.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def save_latest_triage(brain_dir: str | Path, triaged: list[dict]) -> Path:
    """Persiste el triaje para la pestaña Correo de la UI. Solo metadatos:
    ni snippet ni cuerpo llegan al archivo."""
    reports = Path(brain_dir) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    slim = [
        {"priority": m["priority"], "from": m.get("from", ""),
         "subject": m.get("subject", ""), "date": (m.get("date") or "")[:10],
         "account": m.get("account", ""), "reasons": m.get("reasons", []),
         "suggested_action": m.get("suggested_action", "")}
        for m in triaged
    ]
    path = reports / "latest-triage.json"
    path.write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
