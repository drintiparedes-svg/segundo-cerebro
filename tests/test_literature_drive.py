"""Conector de literatura abierta y ampliación de Drive (sin red)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro.connectors.gdrive import BINARY_MIMES, EXPORT_MIMES, TEXT_MIMES
from segundo_cerebro.connectors.literature import result_to_document
from segundo_cerebro.connectors.localfs import read_file_text
from segundo_cerebro.store import BrainStore

EPMC_ITEM = {
    "id": "38012345", "source": "MED", "pmid": "38012345",
    "title": "HPV self-sampling acceptability in Latin America: a systematic review.",
    "authorString": "Narvaez L, Viviano M, Dickson C.",
    "pubYear": "2023", "doi": "10.1016/j.puhip.2023.100417",
    "isOpenAccess": "Y",
    "journalInfo": {"journal": {"title": "Public Health in Practice"}},
    "abstractText": "Self-sampling shows acceptance rates above 80%...",
}


def test_result_to_document():
    doc = result_to_document(EPMC_ITEM)
    assert doc.doc_type == "paper"
    assert doc.date == "2023-01-01"
    assert doc.metadata["open_access"] is True
    assert "Abstract" in doc.body and "80%" in doc.body
    assert doc.path == "europepmc://MED/38012345"


def test_result_without_title_is_skipped():
    assert result_to_document({"id": "1"}) is None


def test_paper_dedup(tmp_path):
    store = BrainStore(tmp_path / "b.db")
    d1 = result_to_document(EPMC_ITEM)
    d2 = result_to_document(EPMC_ITEM)
    assert store.add_document(d1) is True
    assert store.add_document(d2) is False
    store.close()


def test_drive_mime_coverage():
    # planillas Excel y Google Sheets ahora están cubiertas
    assert "application/vnd.google-apps.spreadsheet" in EXPORT_MIMES
    assert any(ext == ".xlsx" for ext in BINARY_MIMES.values())
    assert "application/pdf" in BINARY_MIMES
    assert len(TEXT_MIMES) >= 9


def test_read_xlsx_via_localfs(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Gantt"
    ws.append(["Semana", "Actividad"])
    ws.append([1, "Revisión de literatura VPH"])
    path = tmp_path / "plan.xlsx"
    wb.save(path)
    text = read_file_text(path)
    assert "Gantt" in text and "Revisión de literatura VPH" in text
