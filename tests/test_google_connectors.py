"""Pruebas de los conectores Google (funciones puras + pipeline, sin red)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro.connectors.gcalendar import event_to_document
from segundo_cerebro.connectors.gdrive import drive_file_to_document
from segundo_cerebro.extract import HeuristicExtractor
from segundo_cerebro.ingest import new_summary, process_document
from segundo_cerebro.store import BrainStore

EVENT = {
    "id": "evt123",
    "status": "confirmed",
    "summary": "Comité de datos oncológicos",
    "start": {"dateTime": "2026-09-03T09:00:00-04:00"},
    "attendees": [
        {"email": "ricardo@falp.org", "displayName": "Ricardo"},
        {"email": "dr.intiparedes@gmail.com", "self": True},
    ],
    "organizer": {"displayName": "Ricardo"},
    "description": "Revisión de avance de la base oncohematológica.",
    "htmlLink": "https://calendar.google.com/event?eid=abc",
}


def test_event_to_document():
    doc = event_to_document(EVENT, alias="falp")
    assert doc.doc_type == "meeting"
    assert doc.date == "2026-09-03"
    assert doc.path == "gcal://falp/evt123"
    assert doc.metadata["people"] == ["Ricardo"]   # excluye self
    assert "oncohematológica" in doc.body


def test_event_cancelled_or_untitled_is_skipped():
    assert event_to_document({**EVENT, "status": "cancelled"}, "x") is None
    assert event_to_document({**EVENT, "summary": ""}, "x") is None


def test_drive_file_to_document():
    meta = {
        "id": "f1", "name": "Notas ONCODATA",
        "mimeType": "application/vnd.google-apps.document",
        "modifiedTime": "2026-08-30T12:00:00.000Z",
        "webViewLink": "https://docs.google.com/x",
    }
    doc = drive_file_to_document(meta, "DECISIÓN: usar OMOP como modelo común.", "personal")
    assert doc.path == "gdrive://personal/f1"
    assert doc.date == "2026-08-30"
    assert doc.metadata["source"] == "google-drive"


def test_synced_documents_flow_through_cognitive_layer(tmp_path):
    store = BrainStore(tmp_path / "brain.db")
    extractor = HeuristicExtractor()
    summary = new_summary(extractor)

    doc = event_to_document(EVENT, alias="falp")
    assert store.add_document(doc)
    process_document(store, doc, extractor, summary)

    events = store.list_knowledge_objects(ko_type="event")
    assert any("Comité de datos" in e.title for e in events)
    assert store.find_entities("Ricardo")

    # idempotencia: mismo evento, mismo hash → no se duplica
    assert store.add_document(event_to_document(EVENT, alias="falp")) is False
    store.close()
