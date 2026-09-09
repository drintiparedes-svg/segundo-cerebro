"""Escalamiento: prioridad de áreas, subida, conectores nuevos y validación."""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro.areas import assign_all, load_areas
from segundo_cerebro.connectors.chats import parse_whatsapp, import_export
from segundo_cerebro.connectors.literature import (
    extract_references, verify_document, verify_reference,
)
from segundo_cerebro.connectors.localfs import file_to_document
from segundo_cerebro.connectors.transcripts import parse_transcript, looks_like_transcript
from segundo_cerebro.connectors.zotero import import_library, parse_bibtex
from segundo_cerebro.ingest import ingest_path
from segundo_cerebro.priority import area_scores, load_overrides, set_override
from segundo_cerebro.store import BrainStore

REPO = Path(__file__).resolve().parents[1]
AREAS = load_areas(REPO / "brain" / "self" / "areas.md")
SAMPLE = REPO / "brain" / "inbox" / "2026-08-12-reunion-oncohematologia.md"


@pytest.fixture()
def store(tmp_path):
    s = BrainStore(tmp_path / "b.db")
    ingest_path(s, SAMPLE, prefer_llm=False)
    assign_all(s, AREAS)
    yield s
    s.close()


# ── prioridad ─────────────────────────────────────────────────────────────

def test_scores_rank_active_area_first(store, tmp_path):
    rows = area_scores(store, AREAS, tmp_path)
    assert rows[0]["id"] == "falp"          # tareas+decisión+pregunta
    assert rows[0]["score"] > 0 and rows[0]["rank"] == 1
    assert rows[0]["signals"]["tasks"] == 2


def test_manual_validation_pin_weight_pause(store, tmp_path):
    set_override(tmp_path, "academia", pin=1)
    rows = area_scores(store, AREAS, tmp_path)
    assert rows[0]["id"] == "academia", "pin manda sobre el score"

    set_override(tmp_path, "academia", unpin=True)
    set_override(tmp_path, "falp", status="pausada")
    rows = area_scores(store, AREAS, tmp_path)
    assert rows[-1]["id"] == "falp", "pausada va al final"

    set_override(tmp_path, "clinica", weight=5)
    ov = load_overrides(tmp_path)
    assert ov["clinica"]["weight"] == 5


# ── servidor: override y subida ───────────────────────────────────────────

def test_post_override_and_upload_via_server(store, tmp_path):
    import threading
    from segundo_cerebro.server import BrainHandler
    from http.server import ThreadingHTTPServer

    handler = type("H", (BrainHandler,), {"store": store})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        req = urllib.request.Request(
            f"{base}/api/areas/override",
            data=json.dumps({"id": "academia", "pin": 1}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            payload = json.loads(resp.read())
        assert payload["areas"][0]["id"] == "academia"

        body = "# Nota subida\n\nDECISIÓN: probar la subida manual VPH.".encode()
        req = urllib.request.Request(
            f"{base}/api/upload", data=body,
            headers={"X-Filename": "nota-subida.md"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            payload = json.loads(resp.read())
        assert payload["kos"] >= 1
        assert (Path(store.db_path).parent / "uploads" / "nota-subida.md").exists()
    finally:
        srv.shutdown()


# ── acceso a la fuente: GET /api/doc ──────────────────────────────────────

def test_get_doc_via_server(store):
    import threading
    from segundo_cerebro.server import BrainHandler
    from http.server import ThreadingHTTPServer

    handler = type("H", (BrainHandler,), {"store": store})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    try:
        ko = store.list_knowledge_objects(ko_type="decision", limit=1)[0]
        assert ko.source_doc, "la decisión debe citar su documento"
        with urllib.request.urlopen(f"{base}/api/doc?id={ko.source_doc}") as resp:
            doc = json.loads(resp.read())
        assert doc["found"] and doc["id"] == ko.source_doc
        assert "oncohem" in doc["body"].lower()
        assert doc["title"] and doc["path"]

        with urllib.request.urlopen(f"{base}/api/doc?id=doc-inexistente") as resp:
            assert json.loads(resp.read()) == {"found": False}
    finally:
        srv.shutdown()


# ── conectores nuevos ─────────────────────────────────────────────────────

BIB = """
@article{arbyn2018,
  title = {Detecting cervical precancer by using {HPV} testing on self samples},
  author = {Arbyn, Marc and Smith, Sara B.},
  journal = {BMJ},
  year = {2018},
  doi = {10.1136/bmj.k4823}
}
@book{norman2013, title={The Design of Everyday Things}, author={Norman, Don}, year={2013}}
"""


def test_zotero_bibtex_import(store, tmp_path):
    entries = parse_bibtex(BIB)
    assert len(entries) == 2 and entries[0]["doi"] == "10.1136/bmj.k4823"
    bib = tmp_path / "lib.bib"
    bib.write_text(BIB, encoding="utf-8")
    docs = import_library(store, bib)
    assert len(docs) == 2
    assert docs[0].doc_type == "paper" and docs[0].date == "2018-01-01"
    assert import_library(store, bib) == [], "reimportar no duplica"


def test_whatsapp_parse_and_import(store, tmp_path):
    export = tmp_path / "Chat de WhatsApp con Ricardo.txt"
    export.write_text(
        "12/08/26, 09:14 - Ricardo: ¿Revisaste la propuesta oncohematológica?\n"
        "12/08/26, 09:20 - Inti: Sí, la mando hoy.\n"
        "13/08/26, 18:02 - Ricardo: Perfecto, agendemos.\n", encoding="utf-8")
    days = parse_whatsapp(export.read_text())
    assert set(days) == {"2026-08-12", "2026-08-13"}
    docs = import_export(store, export)
    assert len(docs) == 2 and docs[0].doc_type == "chat"
    assert "Ricardo" in docs[0].metadata["people"]


def test_transcript_detection(tmp_path):
    text = ("Ricardo: Partamos con el registro.\n"
            "Inti: De acuerdo, propongo priorizar el RHC.\n"
            "Raimundo: Yo reviso factibilidad.\n"
            "Ricardo: Cerrado entonces.\n")
    people, clean = parse_transcript(text)
    assert people[0] in ("Ricardo", "Inti") and len(people) == 3
    assert looks_like_transcript(text)
    f = tmp_path / "reunion.txt"
    f.write_text(text, encoding="utf-8")
    doc = file_to_document(f, "test", text)
    assert doc.doc_type == "meeting" and "Raimundo" in doc.metadata["people"]


# ── validación de literatura (fetch simulado, sin red) ────────────────────

CROSSREF_OK = {"message": {
    "title": ["Detecting cervical precancer and reaching underscreened women"],
    "author": [{"family": "Arbyn", "given": "Marc"}],
    "published-print": {"date-parts": [[2018]]},
    "DOI": "10.1136/bmj.k4823",
}}


def test_verify_reference_ok_and_mismatch():
    ref = {"raw": "Arbyn M. Detecting cervical precancer. BMJ. 2018. "
                  "doi:10.1136/bmj.k4823",
           "doi": "10.1136/bmj.k4823", "year": "2018", "author": "Arbyn"}
    result = verify_reference(ref, fetch=lambda url: CROSSREF_OK)
    assert result["verdict"] == "verificado"

    bad = {**ref, "year": "2021"}
    result = verify_reference(bad, fetch=lambda url: CROSSREF_OK)
    assert result["verdict"] == "discrepancia" and "2021" in result["detail"]

    result = verify_reference(ref, fetch=lambda url: {"message": {}})
    assert result["verdict"] == "no_encontrado"


def test_verify_document_report():
    text = ("Referencias\n"
            "1. Arbyn M. Detecting cervical precancer. BMJ. 2018;363:k4823. "
            "doi:10.1136/bmj.k4823\n")
    report, ok, total = verify_document(text, "tesis.md",
                                        fetch=lambda url: CROSSREF_OK)
    assert total == 1 and ok == 1
    assert "[Verificado]" in report and "no fue modificado" in report
