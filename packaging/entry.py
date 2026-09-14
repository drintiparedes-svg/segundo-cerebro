"""Punto de entrada del ejecutable: fija la carpeta del cerebro en el
perfil del usuario y arranca la app de escritorio."""

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    bundle = Path(sys._MEIPASS)                       # recursos empaquetados
    os.chdir(bundle)                                   # brain/self y plantillas relativas
    home = Path.home() / "SegundoCerebro"
    home.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("SB_DB_PATH", str(home / ".brain" / "brain.db"))
    os.environ.setdefault("SB_AREAS", str(home / "areas.md") if (home / "areas.md").exists() else "brain/self/areas.md")

from segundo_cerebro.app.main import main  # noqa: E402

raise SystemExit(main())
