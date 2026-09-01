"""Integración con el escritorio del usuario.

- Detecta la carpeta Escritorio en Windows, macOS y Linux.
- Crea el acceso directo «Segundo Cerebro» que levanta el servidor local
  y abre la UI en el navegador.
- Registra las carpetas del escritorio como fuentes de SOLO LECTURA.

Lo único que se escribe en el escritorio es el archivo del acceso directo;
el contenido de las carpetas jamás se toca.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from .connectors.localfs import add_source

SHORTCUT_NAME = "Segundo Cerebro"


def find_desktop() -> Path | None:
    home = Path.home()
    candidates: list[Path] = []
    if sys.platform == "win32":
        onedrive = os.environ.get("OneDrive") or os.environ.get("ONEDRIVE")
        if onedrive:
            candidates.append(Path(onedrive) / "Desktop")
            candidates.append(Path(onedrive) / "Escritorio")
        candidates += [home / "Desktop", home / "Escritorio"]
    elif sys.platform == "darwin":
        candidates.append(home / "Desktop")
    else:
        # Linux: respetar XDG si está configurado (p. ej. «Escritorio»)
        cfg = home / ".config" / "user-dirs.dirs"
        if cfg.exists():
            m = re.search(r'XDG_DESKTOP_DIR="([^"]+)"', cfg.read_text())
            if m:
                candidates.append(Path(m.group(1).replace("$HOME", str(home))))
        candidates += [home / "Desktop", home / "Escritorio"]
    return next((c for c in candidates if c.is_dir()), None)


def create_shortcut(desktop: Path, project_dir: Path, port: int = 8765) -> Path:
    """Escribe el lanzador según la plataforma y devuelve su ruta."""
    python = sys.executable
    url = f"http://127.0.0.1:{port}"

    if sys.platform == "win32":
        path = desktop / f"{SHORTCUT_NAME}.bat"
        path.write_text(
            "@echo off\r\n"
            f'cd /d "{project_dir}"\r\n'
            f'start "Segundo Cerebro" /min "{python}" -m segundo_cerebro.cli serve --port {port}\r\n'
            "timeout /t 2 >nul\r\n"
            f'start "" {url}\r\n',
            encoding="utf-8",
        )
        return path

    if sys.platform == "darwin":
        path = desktop / f"{SHORTCUT_NAME}.command"
        opener = "open"
    else:
        path = desktop / f"{SHORTCUT_NAME}.sh"
        opener = "xdg-open"
    path.write_text(
        "#!/bin/bash\n"
        f'cd "{project_dir}"\n'
        f'(sleep 2 && {opener} "{url}") &\n'
        f'exec "{python}" -m segundo_cerebro.cli serve --port {port}\n',
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def register_desktop_folders(brain_dir: str | Path, desktop: Path) -> list[dict]:
    """Registra cada subcarpeta del escritorio como fuente de solo lectura
    (una entrada por carpeta: se pueden quitar individualmente con
    `sb sources remove`). Los archivos sueltos del escritorio no se
    incluyen; para eso: `sb sources add ~/Desktop`."""
    registered = []
    for child in sorted(desktop.iterdir()):
        if child.is_dir() and not child.name.startswith("."):
            registered.append(add_source(brain_dir, child))
    return registered
