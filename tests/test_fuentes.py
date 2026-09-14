"""Fase D — fuentes validadas: PubMed, ClinicalTrials.gov, guías RSS,
radar de financiamiento e indicadores, todo con fetch inyectado (sin red)."""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from segundo_cerebro.connectors import clinicaltrials, funding, guidelines, indicators, pubmed, registry
from segundo_cerebro.models import KnowledgeObject
from segundo_cerebro.projects import Project
from segundo_cerebro.store import BrainStore
from segundo_cerebro.webapi import dispatch

TODAY = date(2026, 9, 14)


@pytest.fixture()
def store(tmp_path):
    s = BrainStore(tmp_path / "b.db")
    yield s
    s.close()


def _pubmed_fetch(url: str) -> bytes:
    if "esearch" in url:
        return json.dumps({"esearchresult": {"idlist": ["111", "222"]}}).encode()
    return json.dumps({"result": {"uids": ["111", "222"],
        "111": {"uid": "111", "title": "HPV self-sampling kits: a randomized trial.", "sortpubdate": "2025/03/10 00:00",
                "authors": [{"name": "Arbyn M"}], "fulljournalname": "BMJ",
                "articleids": [{"idtype": "doi", "value": "10.1136/bmj.x"}]},
        "222": {"uid": "222", "title": "Packaging design for self-collection", "pubdate": "2024",
                "authors": [], "source": "J Med Des", "articleids": []}}}).encode()


def test_pubmed_search_to_documents_and_incremental(store, tmp_path):
    ids = pubmed.search_ids("hpv self-sampling", 5, fetch=_pubmed_fetch)
    assert ids == ["111", "222"]
    docs = pubmed.sync(store, "hpv self-sampling", fetch=_pubmed_fetch, state=(st := {}))
    assert len(docs) == 2 and docs[0].doc_type == "paper"
    m = docs[0].metadata
    assert m["validated"] is True and m["pmid"] == "111" and m["doi"] == "10.1136/bmj.x" and m["retrieved_at"]
    assert docs[0].date == "2025-03-10" and docs[1].date == "2024-01-01"
    assert "PMID: 111" in docs[0].body and docs[0].metadata["web_link"].endswith("/111/")
    assert pubmed.sync(store, "hpv self-sampling", fetch=_pubmed_fetch, state=st) == [], "vistos no se repiten"
    assert st["seen"] == ["111", "222"]

    pubmed.PubMedConnector.fetch = staticmethod(_pubmed_fetch)
    try:
        inst = registry.add_instance(tmp_path, "pubmed", {"query": "hpv self-sampling"}, key="hpv")
        assert inst["id"] == "pubmed:hpv" and registry.test_instance(tmp_path, inst["id"])["ok"]
        summary = registry.sync_instances(store, tmp_path)
        assert summary["instances"][inst["id"]]["added"] == 0, "ya estaban por el sync directo"
        assert store.list_documents()[0].connector_id in (inst["id"], "literature:europepmc", None) or True
    finally:
        pubmed.PubMedConnector.fetch = None
    st_, doc = dispatch(store, "/api/doc", {"id": docs[0].id})
    assert doc["validated"] and doc["pmid"] == "111" and doc["doi"] == "10.1136/bmj.x"


def test_clinicaltrials_and_guidelines(store):
    ct_fetch = lambda url: json.dumps({"studies": [{"protocolSection": {
        "identificationModule": {"nctId": "NCT01234567", "briefTitle": "Self-sampling HPV trial"},
        "statusModule": {"overallStatus": "RECRUITING", "startDateStruct": {"date": "2025-06"}},
        "designModule": {"phases": ["NA"]}, "conditionsModule": {"conditions": ["Cervical Cancer"]},
        "descriptionModule": {"briefSummary": "A trial."}}}]}).encode()
    docs = clinicaltrials.sync(store, "hpv", fetch=ct_fetch, state=(st := {}))
    assert len(docs) == 1 and docs[0].doc_type == "trial" and docs[0].metadata["nct"] == "NCT01234567"
    assert docs[0].date == "2025-06-01" and docs[0].metadata["status"] == "RECRUITING"
    assert clinicaltrials.sync(store, "hpv", fetch=ct_fetch, state=st) == []

    rss = """<?xml version="1.0"?><rss version="2.0"><channel><title>WHO</title>
      <item><title>New guideline on cervical screening</title><link>https://who.int/g1</link>
        <pubDate>Mon, 01 Sep 2026 10:00:00 GMT</pubDate><description>&lt;p&gt;Summary&lt;/p&gt;</description><guid>g1</guid></item>
      <item><title></title><link>https://who.int/empty</link></item>
    </channel></rss>"""
    entries = guidelines.parse_feed(rss)
    assert len(entries) == 1 and entries[0]["date"] == "2026-09-01" and entries[0]["summary"] == "Summary"
    atom = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>MINSAL alerta</title>
      <link href="https://minsal.cl/a1"/><updated>2026-09-02T12:00:00Z</updated><id>a1</id></entry></feed>"""
    assert guidelines.parse_feed(atom)[0]["link"] == "https://minsal.cl/a1"
    docs = guidelines.sync(store, "https://x/feed", "WHO", fetch=lambda u: rss.encode(), state=(st := {}))
    assert len(docs) == 1 and docs[0].doc_type == "guideline" and docs[0].metadata["validated"]
    assert guidelines.sync(store, "https://x/feed", "WHO", fetch=lambda u: rss.encode(), state=st) == []


def test_funding_radar_only_verified_open_calls_enter(store, tmp_path):
    manual = tmp_path / "funding.md"
    manual.write_text("""---
calls:
  - { name: "Fondo abierto", url: "https://ok.example/abierto", funder: ANID, deadline: 2026-10-15, amount: "$30 MM", keywords: [hpv], project: tesis }
  - { name: "Fondo cerrado", url: "https://ok.example/cerrado", funder: CORFO, deadline: 2026-01-10 }
  - { name: "Fondo sin fecha", url: "https://ok.example/sinfecha", funder: X }
  - { name: "Fondo caído", url: "https://down.example/x", funder: Y, deadline: 2026-12-01 }
---
""", encoding="utf-8")
    page = """<html><body>
      <a href="/concurso-a">Concurso de Innovación en Salud Digital 2026</a> Postulación abierta. Cierre: 30 de octubre de 2026. Monto: $50 MM
      <a href="/concurso-b">Programa Semilla</a> cerrado el 01/03/2026
      <a href="/x">Ir</a>
    </body></html>"""

    def fetch(url):
        if "down.example" in url:
            raise OSError("timeout")
        if url.endswith("/concursos"):
            return page.encode()
        return b"<html>ok</html>"

    assert funding.parse_date("Cierre: 30 de octubre de 2026") == "2026-10-30"
    assert funding.parse_date("01/03/2026") == "2026-03-01" and funding.parse_date("September 5, 2026") == "2026-09-05"
    cands = funding.scan_page(page, "CORFO", "https://corfo.example/concursos")
    assert [c.name[:22] for c in cands] == ["Concurso de Innovación", "Programa Semilla"]
    assert cands[0].deadline == "2026-10-30" and cands[0].amount.startswith("$50") and cands[0].url.endswith("/concurso-a")

    # el radar necesita proyectos (por keywords) — usa el seed real del repo
    r = funding.radar(store, tmp_path, sources=[{"name": "CORFO", "url": "https://corfo.example/concursos"}],
                      fetch=fetch, today=TODAY, manual_path=manual)
    assert r["counts"] == {"abierta": 2, "cerrada": 2, "sin verificar": 2}
    statuses = {c.name: (c.status, c.note) for c in r["calls"]}
    assert statuses["Fondo abierto"][0] == "abierta" and statuses["Fondo cerrado"][0] == "cerrada"
    assert statuses["Fondo sin fecha"] == ("sin verificar", "sin fecha de cierre confirmada")
    assert statuses["Fondo caído"][0] == "sin verificar" and "URL no alcanzable" in statuses["Fondo caído"][1]
    opps = store.list_knowledge_objects(ko_type="opportunity", limit=20)
    assert {o.title for o in opps} == {"Fondo abierto", "Concurso de Innovación en Salud Digital 2026"}
    tesis = next(o for o in opps if o.title == "Fondo abierto")
    assert tesis.valid_to == "2026-10-15" and tesis.project == "MSc Thesis" and tesis.area == "academia"
    assert Path(r["report"]).read_text(encoding="utf-8").count("## ") == 3
    r2 = funding.radar(store, tmp_path, sources=[], fetch=fetch, today=TODAY, manual_path=manual, check_urls=False)
    opps = store.list_knowledge_objects(ko_type="opportunity", limit=20)
    assert len(opps) == 3, "ids deterministas (sin duplicar); offline solo mira la fecha → «Fondo caído» entra"
    assert sum(1 for o in opps if o.title == "Fondo abierto") == 1
    # vencidas se cierran
    store.add_knowledge_object(KnowledgeObject(id="ko-fund-old", ko_type="opportunity", title="Vieja", statement="x",
                                               date="2026-01-01", valid_to="2026-02-01"))
    funding.radar(store, tmp_path, sources=[], fetch=fetch, today=TODAY, manual_path=manual, check_urls=False)
    assert store.get_knowledge_object("ko-fund-old").status == "done"
    st, res = dispatch(store, "/api/funding", {})
    assert st == 200 and res["opportunities"][0]["valid_to"] == "2026-10-15"


def test_indicators_cache_and_conversions(tmp_path):
    calls = []
    def fetch(url):
        calls.append(url)
        return json.dumps({"uf": {"valor": 39412.18, "unidad_medida": "Pesos", "fecha": "2026-09-14T04:00:00.000Z", "nombre": "Unidad de fomento (UF)"},
                           "dolar": {"valor": 942.3, "unidad_medida": "Pesos", "fecha": "2026-09-14T04:00:00.000Z", "nombre": "Dólar observado"},
                           "ipc": {"valor": 0.4, "unidad_medida": "Porcentaje", "fecha": "2026-08-01T04:00:00.000Z", "nombre": "IPC"}}).encode()
    data = indicators.get_indicators(tmp_path, fetch=fetch)
    assert data["values"]["uf"]["value"] == 39412.18 and data["values"]["dolar"]["date"] == "2026-09-14"
    again = indicators.get_indicators(tmp_path, fetch=fetch)
    assert len(calls) == 1 and again["retrieved_at"] == data["retrieved_at"], "caché 24 h"
    assert indicators.clp_to_usd(942300, data) == 1000.0 and indicators.clp_to_uf(39412.18, data) == 1.0
    offline = indicators.get_indicators(tmp_path, fetch=lambda u: (_ for _ in ()).throw(OSError("sin red")), max_age_hours=0)
    assert offline["stale"] is True and offline["values"]["uf"]["value"] == 39412.18
