"""Interruptor de emergencia de la IA.

Un solo interruptor apaga TODO lo que llama a Claude o actúa por su cuenta
y deja el sistema en **modo manual supervisado**: extracción heurística,
triaje local, borradores de andamiaje, sin tarea programada. Nada de lo
que ya está en tu memoria se toca.

La compuerta es de código, no de interfaz: todo cliente de Claude se crea
con `ai.client()`, que se niega si el interruptor está apagado. El estado
vive en un archivo marcador (`.brain/AI_OFF`) para que cualquier proceso
—CLI, servidor, tarea programada— lo vea sin coordinación; `SB_AI_OFF=1`
en el entorno apaga igual.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

MARKER = "AI_OFF"


class AIDisabled(RuntimeError):
    """Se intentó usar Claude con la IA apagada (modo manual supervisado)."""


def default_brain_dir() -> Path:
    return Path(os.environ.get("SB_DB_PATH", ".brain/brain.db")).parent


def marker_path(brain_dir: str | Path | None = None) -> Path:
    return Path(brain_dir or default_brain_dir()) / MARKER


def is_off(brain_dir: str | Path | None = None) -> bool:
    if os.environ.get("SB_AI_OFF", "").lower() in ("1", "true", "yes", "on"):
        return True
    return marker_path(brain_dir).exists()


def status(brain_dir: str | Path | None = None) -> dict:
    path = marker_path(brain_dir)
    info = {"enabled": not is_off(brain_dir), "mode": "manual supervisado" if is_off(brain_dir)
            else "asistido", "off_at": None, "reason": None,
            "env_forced": os.environ.get("SB_AI_OFF", "").lower() in ("1", "true", "yes", "on")}
    if path.exists():
        try:
            info.update({k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items()
                         if k in ("off_at", "reason", "schedule_removed")})
        except (json.JSONDecodeError, OSError):
            pass
    return info


def client():
    """Único constructor del cliente de Claude en todo el sistema."""
    if is_off():
        raise AIDisabled("IA apagada: modo manual supervisado. Reactiva con `sb ai on`.")
    import anthropic
    return anthropic.Anthropic()


def _log(brain_dir: Path, line: str) -> None:
    logs = brain_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / "ai-switch.log").open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {line}\n")


def switch_off(brain_dir: str | Path | None = None, reason: str = "",
               remove_schedule: bool = True, scheduler=None) -> dict:
    """Apaga la IA y toda automatización. Idempotente. Devuelve el estado."""
    from .config import load_config, save_config
    brain_dir = Path(brain_dir or default_brain_dir())
    brain_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_config(brain_dir)
    backup = {"llm_areas": cfg["llm"].get("areas", []),
              "refresh_auto": cfg["refresh"].get("auto", True)}
    cfg["llm"]["areas"] = []          # ninguna área habilitada para Claude
    cfg["refresh"]["auto"] = False    # nada corre solo: ni servicio ni acceso directo
    save_config(brain_dir, cfg)

    schedule_removed = None
    if remove_schedule:
        try:
            sched = scheduler or __import__("segundo_cerebro.scheduler", fromlist=["remove"])
            schedule_removed = bool(sched.remove().get("removed"))
        except Exception as exc:   # sin crontab/schtasks disponible: se registra, no se cae
            schedule_removed = f"no se pudo quitar: {exc}"

    path = marker_path(brain_dir)
    if not path.exists():
        path.write_text(json.dumps({
            "off_at": datetime.now().isoformat(timespec="seconds"), "reason": reason,
            "backup": backup, "schedule_removed": schedule_removed,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(brain_dir, f"OFF · {reason or 'sin motivo'} · tarea programada: {schedule_removed}")
    return status(brain_dir)


def switch_on(brain_dir: str | Path | None = None) -> dict:
    """Reactiva la IA restaurando la política previa. La tarea programada NO
    se reinstala sola: eso lo decides tú con `sb schedule install`."""
    from .config import load_config, save_config
    brain_dir = Path(brain_dir or default_brain_dir())
    path = marker_path(brain_dir)
    backup = {}
    if path.exists():
        try:
            backup = json.loads(path.read_text(encoding="utf-8")).get("backup", {})
        except (json.JSONDecodeError, OSError):
            backup = {}
        path.unlink()
    cfg = load_config(brain_dir)
    cfg["llm"]["areas"] = backup.get("llm_areas", cfg["llm"].get("areas", []))
    cfg["refresh"]["auto"] = True
    save_config(brain_dir, cfg)
    _log(brain_dir, f"ON · áreas Claude restauradas: {cfg['llm']['areas'] or 'ninguna'}")
    return {**status(brain_dir), "restored_llm_areas": cfg["llm"]["areas"],
            "schedule_note": "la tarea programada no se reinstala sola: sb schedule install"}
