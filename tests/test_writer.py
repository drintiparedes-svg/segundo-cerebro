"""Writing agent: plantillas, material desde la memoria y andamiaje local."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro.agents.writer import (
    MATERIAL_MARK, draft, gather_material, list_templates, load_template,
    save_draft, scaffold,
)
from segundo_cerebro.areas import assign_all, load_areas
from segundo_cerebro.ingest import ingest_path
from segundo_cerebro.store import BrainStore

REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "brain" / "templates" / "drafts"
SAMPLE = REPO / "brain" / "inbox" / "2026-08-12-reunion-oncohematologia.md"


@pytest.fixture()
def store(tmp_path):
    s = BrainStore(tmp_path / "b.db")
    ingest_path(s, SAMPLE, prefer_llm=False)
    assign_all(s, load_areas(REPO / "brain" / "self" / "areas.md"))
    yield s
    s.close()


def test_templates_exist_and_have_material_mark():
    kinds = list_templates(TEMPLATES)
    assert {"onepager", "informe-academico", "plan-trabajo",
            "minuta", "informe-gestion"} <= set(kinds)
    for kind in kinds:
        template = load_template(kind, TEMPLATES)
        assert MATERIAL_MARK in template, f"{kind} sin marca de material"


def test_gather_material_cites_sources(store):
    material = gather_material(store, "base oncohematológica", area="falp")
    assert material["decisions"] and material["tasks"]
    assert all(k["source"] for k in material["decisions"])


def test_scaffold_fills_topic_and_material(store):
    template = load_template("minuta", TEMPLATES)
    material = gather_material(store, "oncohematológica")
    out = scaffold(template, "Comité de datos", material)
    assert "Comité de datos" in out
    assert "Material desde tu memoria" in out
    assert "oncohematológicos" in out
    assert MATERIAL_MARK not in out


def test_draft_local_end_to_end(store, tmp_path):
    markdown, mode = draft(store, "informe-gestion", "avance oncohematología",
                           area="falp", prefer_llm=False,
                           templates_dir=TEMPLATES)
    assert mode == "local"
    assert "Informe de gestión" in markdown
    path = save_draft(tmp_path, "informe-gestion", markdown)
    assert path.exists() and path.parent.name == "drafts"
    # segundo borrador del mismo día no sobrescribe
    path2 = save_draft(tmp_path, "informe-gestion", markdown)
    assert path2 != path


def test_draft_unknown_kind(store):
    with pytest.raises(FileNotFoundError):
        draft(store, "no-existe", "x", templates_dir=TEMPLATES)
