"""Fase E — app de escritorio: token de sesión en el servidor, doctor,
primeros pasos, empaquetado (dry-run), versión y aviso de actualización."""

import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro import __version__
from segundo_cerebro.app import main as app_main
from segundo_cerebro.app.updates import check_latest
from segundo_cerebro.doctor import run_doctor, setup_status
from segundo_cerebro.server import make_server
from segundo_cerebro.store import BrainStore
from segundo_cerebro.ui import render_page
from segundo_cerebro.webapi import dispatch, dispatch_post

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("SB_DB_PATH", str(tmp_path / "b.db"))
    s = BrainStore(tmp_path / "b.db")
    yield s
    s.close()


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_server_token_gates_api_and_page(store):
    server = make_server(store, "127.0.0.1", 0, token="secreto123")
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        assert _get(f"{base}/api/status")[0] == 401
        assert _get(f"{base}/")[0] == 401
        st, body = _get(f"{base}/?token=secreto123")
        assert st == 200 and b'<meta name="sb-token" content="secreto123">' in body
        assert _get(f"{base}/api/status", {"X-SB-Token": "secreto123"})[0] == 200
        assert _get(f"{base}/api/status?token=secreto123")[0] == 200
        req = urllib.request.Request(f"{base}/api/areas/override", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req)
            assert False, "POST sin token debe fallar"
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
    finally:
        server.shutdown()
    assert '<meta name="sb-token"' not in render_page(), "sb serve clásico: sin token"
    plain = make_server(store, "127.0.0.1", 0)
    p2 = plain.server_address[1]
    threading.Thread(target=plain.serve_forever, daemon=True).start()
    try:
        assert _get(f"http://127.0.0.1:{p2}/api/status")[0] == 200
    finally:
        plain.shutdown()


def test_app_helpers_and_version():
    port = app_main.find_free_port()
    assert 1024 < port < 65536
    t1, t2 = app_main.make_token(), app_main.make_token()
    assert len(t1) >= 30 and t1 != t2
    assert __version__ == "0.2.0"
    out = subprocess.run([sys.executable, "-m", "segundo_cerebro.cli", "--version"], capture_output=True, text=True,
                         env={"PYTHONPATH": str(REPO / "src"), "PATH": "/usr/bin:/bin"})
    assert out.stdout.strip() == f"sb {__version__}"


def test_doctor_and_setup(store, tmp_path, monkeypatch):
    monkeypatch.chdir(REPO)
    result = run_doctor(tmp_path, store, test_connectors=False)
    ids = {c["id"]: c for c in result["checks"]}
    assert ids["python"]["ok"] and ids["dep:pyyaml"]["ok"] and ids["brain_dir"]["ok"]
    assert ids["memory"]["level"] == "warn" and "sb sources suggest" in ids["memory"]["fix"]
    assert ids["google"]["level"] == "warn" and ids["refresh"]["level"] == "warn" and ids["ai"]["ok"]
    assert ids["seed:areas.md"]["ok"] and result["healthy"] and result["version"] == __version__
    assert result["summary"]["fail"] == 0

    st = setup_status(tmp_path, store)
    assert st["total"] == 6 and st["done"] == 0 and not st["complete"]
    assert {s["id"] for s in st["steps"]} >= {"sources", "memory", "google", "people", "llm", "schedule"}

    from segundo_cerebro.connectors import registry
    folder = tmp_path / "Docs"; folder.mkdir(); (folder / "n.md").write_text("# n\n\nDECISIÓN: x.")
    registry.add_instance(tmp_path, "localfs", {"path": str(folder)})
    registry.sync_instances(store, tmp_path)
    from segundo_cerebro.people import set_person_override
    set_person_override(tmp_path, "Ricardo", pin=True)
    st = setup_status(tmp_path, store)
    done = {s["id"] for s in st["steps"] if s["done"]}
    assert {"sources", "memory", "people"} <= done

    status, res = dispatch(store, "/api/setup", {})
    assert status == 200 and res["done"] == st["done"]
    status, res = dispatch(store, "/api/doctor", {"connectors": "0"})
    assert status == 200 and res["healthy"]
    status, res = dispatch(store, "/api/status", {})
    assert res["version"] == __version__
    status, res = dispatch_post(store, "/api/schedule/install", {}, json.dumps({"every": "2h", "dry_run": True}).encode())
    assert status == 200 and res["dry_run"] and res["minutes"] == 120


def test_build_script_dry_run_and_update_check():
    out = subprocess.run([sys.executable, str(REPO / "packaging" / "build_app.py"), "--dry-run"],
                         capture_output=True, text=True, cwd=REPO)
    assert out.returncode == 0 and "PyInstaller" in out.stdout and "--windowed" in out.stdout
    assert "index.html" in out.stdout and "brain/templates" in out.stdout and "entry.py" in out.stdout
    assert ".brain" not in out.stdout, "la memoria nunca se empaqueta"

    fake = lambda url: json.dumps({"tag_name": "v9.9.9", "html_url": "https://x/rel", "body": "notas"}).encode()
    r = check_latest(fetch=fake)
    assert r["update"] and r["latest"] == "9.9.9" and r["current"] == __version__
    same = check_latest(fetch=lambda u: json.dumps({"tag_name": f"v{__version__}"}).encode())
    assert same["update"] is False
    err = check_latest(fetch=lambda u: (_ for _ in ()).throw(OSError("sin red")))
    assert err["error"] and err["update"] is False
    assert (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8").count("runs-on") >= 3
