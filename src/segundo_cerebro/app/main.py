"""Segundo Cerebro como aplicación de escritorio.

Levanta el servidor local en un puerto libre con un **token de sesión**
(solo esta ventana puede hablar con la API), lanza `sb refresh` en segundo
plano si la configuración lo permite, y abre una ventana nativa
(pywebview). Sin pywebview, abre tu navegador: el sistema es el mismo.

    python -m segundo_cerebro.app [--db RUTA] [--no-refresh] [--browser]
"""

from __future__ import annotations

import argparse
import os
import secrets
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from .. import __version__
from ..store import BrainStore

DEFAULT_HOME = Path.home() / "SegundoCerebro"


def default_db() -> Path:
    env = os.environ.get("SB_DB_PATH")
    if env:
        return Path(env)
    if Path(".brain").is_dir():
        return Path(".brain/brain.db")
    return DEFAULT_HOME / ".brain" / "brain.db"


def find_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def make_token() -> str:
    return secrets.token_urlsafe(24)


def start_server(store: BrainStore, host: str, port: int, token: str):
    from ..server import make_server
    server = make_server(store, host=host, port=port, token=token)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def background_refresh(store: BrainStore, brain_dir: Path) -> None:
    from ..config import load_config
    from ..refresh import run_refresh
    if not load_config(brain_dir)["refresh"].get("auto", True):
        return   # modo manual supervisado: nada corre solo
    threading.Thread(target=run_refresh, args=(store, brain_dir), daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="segundo-cerebro", description="Segundo Cerebro · app de escritorio")
    parser.add_argument("--db", default=str(default_db()))
    parser.add_argument("--port", type=int, default=0, help="0 = puerto libre")
    parser.add_argument("--no-refresh", action="store_true")
    parser.add_argument("--browser", action="store_true", help="abrir en el navegador en vez de ventana nativa")
    parser.add_argument("--version", action="version", version=f"Segundo Cerebro {__version__}")
    args = parser.parse_args(argv)

    db = Path(args.db).expanduser()
    db.parent.mkdir(parents=True, exist_ok=True)
    os.environ["SB_DB_PATH"] = str(db)
    store = BrainStore(db)
    brain_dir = db.parent
    host = "127.0.0.1"
    port = args.port or find_free_port(host)
    token = make_token()
    server = start_server(store, host, port, token)
    url = f"http://{host}:{port}/?token={token}"
    if not args.no_refresh:
        background_refresh(store, brain_dir)

    if not args.browser:
        try:
            import webview
        except ImportError:
            webview = None
        if webview is not None:
            window = webview.create_window("Segundo Cerebro", url, width=1380, height=880, min_size=(960, 640))
            try:
                webview.start()
            finally:
                server.shutdown()
            return 0
        print("pywebview no está instalado (pip install -e '.[app]'); abro el navegador.", file=sys.stderr)
    print(f"Segundo Cerebro {__version__} → {url}")
    webbrowser.open(url)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()
    return 0
