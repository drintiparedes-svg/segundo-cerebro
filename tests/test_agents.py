"""Agentes: curador de archivos y triaje de correo (modo local, sin red)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro.agents.curator import heuristic_grouping, organize
from segundo_cerebro.agents.mail_triage import heuristic_triage, to_markdown
from segundo_cerebro.connectors.gmail import extract_body, message_to_email, sender_name
from segundo_cerebro.connectors.localfs import read_file_text
from segundo_cerebro.ingest import ingest_path
from segundo_cerebro.store import BrainStore

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "brain" / "inbox" / "2026-08-12-reunion-oncohematologia.md"


@pytest.fixture()
def store(tmp_path):
    s = BrainStore(tmp_path / "brain.db")
    ingest_path(s, SAMPLE, prefer_llm=False)
    yield s
    s.close()


# ── curador ───────────────────────────────────────────────────────────────

def test_curator_heuristic_groups_by_source(store):
    collections = organize(store, prefer_llm=False)
    assert collections
    assert store.list_collections(), "la agrupación debe persistirse"
    all_docs = {d.id for d in store.list_documents()}
    grouped = {i for c in collections for i in c["doc_ids"]}
    assert grouped == all_docs, "cada documento queda en una colección"


def test_curator_rerun_replaces_not_duplicates(store):
    organize(store, prefer_llm=False)
    organize(store, prefer_llm=False)
    cols = store.list_collections()
    names = [c["name"] for c in cols]
    assert len(names) == len(set(names))


# ── triaje de correo ──────────────────────────────────────────────────────

def _mail(**kw):
    base = {"id": "m1", "account": "falp", "from": "X <x@y.com>", "to": "",
            "subject": "", "date": "", "snippet": "", "labels": [], "body": ""}
    return {**base, **kw}


def test_triage_boosts_known_people_from_graph(store):
    mails = [
        _mail(id="a", **{"from": "Ricardo <r@falp.org>"},
              subject="Revisar propuesta antes del plazo de mañana"),
        _mail(id="b", **{"from": "Ofertas <no-reply@tienda.com>"},
              subject="Newsletter: 50% de descuento",
              labels=["CATEGORY_PROMOTIONS"]),
    ]
    triaged = heuristic_triage(mails, store)
    assert triaged[0]["id"] == "a" and triaged[0]["priority"] <= 2
    assert triaged[-1]["id"] == "b" and triaged[-1]["priority"] == 5
    assert any("knowledge graph" in r for r in triaged[0]["reasons"])


def test_triage_report_groups_by_priority(store):
    mails = [_mail(id="a", subject="hola"), _mail(id="b", subject="chau")]
    report = to_markdown(heuristic_triage(mails, store))
    assert "Triaje de correo" in report
    assert "no fue modificada" in report


def test_triage_never_mutates_input(store):
    mails = [_mail(id="a", subject="Urgente: firma hoy")]
    before = dict(mails[0])
    heuristic_triage(mails, store)
    assert mails[0] == before


# ── conversores Gmail ─────────────────────────────────────────────────────

def test_message_to_email_and_sender():
    msg = {
        "id": "abc", "snippet": "te adjunto la minuta…",
        "labelIds": ["INBOX"],
        "payload": {"headers": [
            {"name": "From", "value": '"Ricardo Morales" <r@falp.org>'},
            {"name": "Subject", "value": "Minuta comité"},
            {"name": "Date", "value": "Mon, 31 Aug 2026 10:00:00 -0400"},
        ]},
    }
    mail = message_to_email(msg, "falp")
    assert mail["subject"] == "Minuta comité"
    assert mail["date"].startswith("2026-08-31")
    assert sender_name(mail["from"]) == "Ricardo Morales"


def test_extract_body_walks_mime_parts():
    import base64
    data = base64.urlsafe_b64encode("hola cuerpo".encode()).decode()
    payload = {"mimeType": "multipart/alternative", "parts": [
        {"mimeType": "text/html", "body": {"data": "x"}},
        {"mimeType": "text/plain", "body": {"data": data}},
    ]}
    assert extract_body(payload) == "hola cuerpo"


# ── lectores nuevos ───────────────────────────────────────────────────────

def test_read_html_and_json(tmp_path):
    html = tmp_path / "pagina.html"
    html.write_text("<html><style>a{}</style><body><h1>Título</h1>"
                    "<p>contenido útil</p></body></html>", encoding="utf-8")
    text = read_file_text(html)
    assert "contenido útil" in text and "a{}" not in text

    j = tmp_path / "datos.json"
    j.write_text('{"proyecto": "ONCODATA"}', encoding="utf-8")
    assert "ONCODATA" in read_file_text(j)
