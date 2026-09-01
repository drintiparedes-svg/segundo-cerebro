"""Capa de agentes (inicio del V4 del roadmap).

Principios no negociables (docs/10-agentes-y-privacidad.md):
- Los agentes LEEN y RECOMIENDAN; nunca ejecutan acciones externas.
- Todo informe se guarda solo en .brain/reports/ (local, fuera de git).
- Cada agente tiene un modo 100% local (--no-llm) en el que ningún dato
  sale de la máquina.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def save_report(brain_dir: str | Path, kind: str, markdown: str) -> Path:
    reports = Path(brain_dir) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    path = reports / f"{kind}-{stamp}.md"
    path.write_text(markdown, encoding="utf-8")
    return path
