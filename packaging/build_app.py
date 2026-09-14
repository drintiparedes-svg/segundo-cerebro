"""Empaqueta la app de escritorio con PyInstaller (Windows .exe / macOS .app).

    pip install -e ".[app,files,google,build]"
    python packaging/build_app.py            # dist/Segundo Cerebro/
    python packaging/build_app.py --dry-run  # muestra el comando

El paquete incluye la UI, las plantillas de borradores y las semillas de
brain/self. La memoria (.brain/) NUNCA se empaqueta: vive en
~/SegundoCerebro/.brain en el equipo del usuario.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "Segundo Cerebro"
ENTRY = ROOT / "packaging" / "entry.py"
SEP = ";" if sys.platform == "win32" else ":"


def data_args() -> list[str]:
    pairs = [
        (ROOT / "src" / "segundo_cerebro" / "ui" / "index.html", "segundo_cerebro/ui"),
        (ROOT / "brain" / "templates", "brain/templates"),
        (ROOT / "brain" / "self" / "areas.md", "brain/self"),
        (ROOT / "brain" / "self" / "projects.md", "brain/self"),
        (ROOT / "brain" / "self" / "funding.md", "brain/self"),
        (ROOT / "brain" / "README.md", "brain"),
    ]
    out = []
    for src, dest in pairs:
        if src.exists():
            out += ["--add-data", f"{src}{SEP}{dest}"]
    return out


def command(onefile: bool = False) -> list[str]:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
           "--name", NAME, "--paths", str(ROOT / "src"),
           "--collect-submodules", "segundo_cerebro",
           "--hidden-import", "segundo_cerebro.connectors.registry",
           "--hidden-import", "segundo_cerebro.app.main"]
    cmd += ["--onefile"] if onefile else ["--onedir"]
    icon = ROOT / "packaging" / ("icon.ico" if sys.platform == "win32" else "icon.icns")
    if icon.exists():
        cmd += ["--icon", str(icon)]
    cmd += data_args()
    cmd.append(str(ENTRY))
    return cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--onefile", action="store_true")
    args = parser.parse_args(argv)
    cmd = command(args.onefile)
    print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
    if args.dry_run:
        return 0
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.call(cmd, cwd=ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
