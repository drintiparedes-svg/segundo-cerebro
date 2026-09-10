"""`sb schedule`: programa `sb refresh` en el programador nativo del sistema.

Sin servicios en la nube ni permisos de administrador: una tarea de usuario
en Windows (schtasks), un LaunchAgent en macOS o una línea de crontab en
Linux. `dry_run=True` muestra lo que haría sin tocar nada.
"""

from __future__ import annotations

import plistlib
import re
import shlex
import subprocess
import sys
from pathlib import Path

TASK_NAME = "SegundoCerebro Refresh"
LABEL = "cl.segundocerebro.refresh"
CRON_TAG = "# segundo-cerebro refresh"


def parse_every(text: str | int) -> int:
    """'4h' → 240 min · '90m' → 90 · 4 → 240 (horas por defecto)."""
    if isinstance(text, int):
        return text * 60
    m = re.fullmatch(r"\s*(\d+)\s*([hm]?)\s*", str(text))
    if not m:
        raise ValueError(f"intervalo inválido: {text!r} (usa 4h o 90m)")
    n, unit = int(m.group(1)), m.group(2) or "h"
    minutes = n * 60 if unit == "h" else n
    return max(15, minutes)


def refresh_command(project_dir: Path, db: str, python: str | None = None) -> list[str]:
    python = python or sys.executable
    return [python, "-m", "segundo_cerebro.cli", "--db", db, "refresh", "--quiet"]


def plan(project_dir: Path, db: str, every: str | int = "4h",
         platform: str | None = None, python: str | None = None,
         home: Path | None = None) -> dict:
    """Describe la instalación para la plataforma (sin ejecutar nada)."""
    platform = platform or sys.platform
    home = home or Path.home()
    minutes = parse_every(every)
    cmd = refresh_command(project_dir, db, python)
    if platform == "win32":
        inner = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        tr = f'cmd /c cd /d "{project_dir}" && {inner}'
        return {"platform": "windows", "minutes": minutes, "commands": [
            ["schtasks", "/Create", "/F", "/SC", "MINUTE", "/MO", str(minutes),
             "/TN", TASK_NAME, "/TR", tr],
            ["schtasks", "/Create", "/F", "/SC", "ONLOGON",
             "/TN", TASK_NAME + " (inicio)", "/TR", tr],
        ]}
    if platform == "darwin":
        path = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        plist = {"Label": LABEL, "ProgramArguments": cmd,
                 "WorkingDirectory": str(project_dir),
                 "StartInterval": minutes * 60, "RunAtLoad": True,
                 "StandardOutPath": str(project_dir / ".brain" / "logs" / "launchd.out"),
                 "StandardErrorPath": str(project_dir / ".brain" / "logs" / "launchd.err")}
        return {"platform": "macos", "minutes": minutes, "plist_path": str(path),
                "plist": plist, "commands": [["launchctl", "unload", str(path)],
                                             ["launchctl", "load", str(path)]]}
    hours = max(1, minutes // 60)
    spec = f"0 */{hours} * * *" if minutes >= 60 else f"*/{minutes} * * * *"
    line = (f"{spec} cd {shlex.quote(str(project_dir))} && "
            f"{' '.join(shlex.quote(c) for c in cmd)} >/dev/null 2>&1 {CRON_TAG}")
    return {"platform": "linux", "minutes": minutes, "cron_line": line}


def install(project_dir: Path, db: str, every: str | int = "4h",
            platform: str | None = None, python: str | None = None,
            home: Path | None = None, dry_run: bool = False) -> dict:
    p = plan(project_dir, db, every, platform, python, home)
    if dry_run:
        return {**p, "dry_run": True}
    if p["platform"] == "windows":
        for cmd in p["commands"]:
            subprocess.run(cmd, check=True, capture_output=True)
    elif p["platform"] == "macos":
        path = Path(p["plist_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            plistlib.dump(p["plist"], f)
        subprocess.run(p["commands"][0], capture_output=True)   # unload puede fallar
        subprocess.run(p["commands"][1], check=True, capture_output=True)
    else:
        current = _crontab()
        kept = [l for l in current.splitlines() if CRON_TAG not in l]
        kept.append(p["cron_line"])
        _write_crontab("\n".join(kept) + "\n")
    return {**p, "installed": True}


def remove(platform: str | None = None, home: Path | None = None,
           dry_run: bool = False) -> dict:
    platform = platform or sys.platform
    home = home or Path.home()
    if platform == "win32":
        cmds = [["schtasks", "/Delete", "/F", "/TN", TASK_NAME],
                ["schtasks", "/Delete", "/F", "/TN", TASK_NAME + " (inicio)"]]
        if not dry_run:
            for cmd in cmds:
                subprocess.run(cmd, capture_output=True)
        return {"platform": "windows", "commands": cmds, "removed": not dry_run}
    if platform == "darwin":
        path = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        if not dry_run:
            subprocess.run(["launchctl", "unload", str(path)], capture_output=True)
            path.unlink(missing_ok=True)
        return {"platform": "macos", "plist_path": str(path), "removed": not dry_run}
    if not dry_run:
        kept = [l for l in _crontab().splitlines() if CRON_TAG not in l]
        _write_crontab(("\n".join(kept) + "\n") if kept else "")
    return {"platform": "linux", "removed": not dry_run}


def status(platform: str | None = None, home: Path | None = None) -> dict:
    platform = platform or sys.platform
    home = home or Path.home()
    if platform == "win32":
        r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME],
                           capture_output=True, text=True)
        return {"platform": "windows", "installed": r.returncode == 0,
                "detail": r.stdout.strip()[-400:]}
    if platform == "darwin":
        path = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        return {"platform": "macos", "installed": path.exists(), "detail": str(path)}
    lines = [l for l in _crontab().splitlines() if CRON_TAG in l]
    return {"platform": "linux", "installed": bool(lines), "detail": "\n".join(lines)}


def _crontab() -> str:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def _write_crontab(content: str) -> None:
    subprocess.run(["crontab", "-"], input=content, text=True, check=True)
