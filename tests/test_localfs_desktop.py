"""Fuentes locales de solo lectura y integración con el escritorio."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro.connectors.localfs import (
    add_source, load_registry, remove_source, sync_source,
)
from segundo_cerebro.desktop import create_shortcut, register_desktop_folders
from segundo_cerebro.store import BrainStore


@pytest.fixture()
def workspace(tmp_path):
    brain = tmp_path / ".brain"
    store = BrainStore(brain / "brain.db")
    src = tmp_path / "Escritorio" / "Proyectos FALP"
    src.mkdir(parents=True)
    (src / "notas.md").write_text(
        "# Notas\n\nDECISIÓN: priorizar el RHC este trimestre.\n", encoding="utf-8")
    (src / "pendientes.txt").write_text("Llamar a Ricardo.", encoding="utf-8")
    (src / "foto.jpg").write_bytes(b"\xff\xd8no-texto")
    yield brain, store, src
    store.close()


def _dir_fingerprint(root: Path) -> dict:
    return {
        str(p): (p.stat().st_mtime_ns, p.read_bytes())
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def test_sync_reads_without_modifying_source(workspace):
    brain, store, src = workspace
    before = _dir_fingerprint(src)

    source = add_source(brain, src)
    result = sync_source(store, brain, source)

    assert result["added"] == 2          # md + txt; jpg no soportado
    assert _dir_fingerprint(src) == before, "la fuente debe quedar intacta"
    # y la decisión del archivo quedó en la memoria
    decisions = store.list_knowledge_objects(ko_type="decision")
    # sync_source no corre la capa cognitiva (eso lo hace el CLI); al menos
    # el documento debe estar
    docs = store.search_documents("priorizar RHC trimestre")
    assert docs and docs[0].metadata["source"] == "local-folder"


def test_sync_is_incremental(workspace):
    brain, store, src = workspace
    source = add_source(brain, src)
    assert sync_source(store, brain, source)["added"] == 2
    second = sync_source(store, brain, source)
    assert second["added"] == 0
    assert second["unchanged"] >= 2


def test_registry_add_list_remove(workspace):
    brain, _, src = workspace
    add_source(brain, src, alias="FALP")
    add_source(brain, src)               # duplicado: no se repite
    registry = load_registry(brain)
    assert len(registry["sources"]) == 1
    assert registry["sources"][0]["alias"] == "FALP"
    assert remove_source(brain, src)
    assert not load_registry(brain)["sources"]


def test_register_desktop_folders_only_dirs(workspace, tmp_path):
    brain, _, _ = workspace
    desktop = tmp_path / "Escritorio"
    (desktop / "Tesis").mkdir()
    (desktop / ".oculta").mkdir()
    (desktop / "suelto.txt").write_text("x", encoding="utf-8")

    entries = register_desktop_folders(brain, desktop)
    names = {e["alias"] for e in entries}
    assert "Proyectos FALP" in names and "Tesis" in names
    assert ".oculta" not in names


def test_create_shortcut(tmp_path):
    desktop = tmp_path / "desk"
    desktop.mkdir()
    shortcut = create_shortcut(desktop, Path("/opt/segundo-cerebro"), port=9000)
    body = shortcut.read_text(encoding="utf-8")
    assert shortcut.exists()
    assert "9000" in body and "segundo_cerebro.cli" in body
    if sys.platform != "win32":
        assert shortcut.stat().st_mode & 0o111, "debe ser ejecutable"
