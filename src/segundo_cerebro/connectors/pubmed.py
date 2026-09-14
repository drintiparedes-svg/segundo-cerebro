"""PubMed (NCBI E-utilities, API pública oficial) → papers con PMID/DOI.

Búsquedas guardadas: `sb literature watch "hpv self-sampling" --source pubmed`
crea una instancia `pubmed:<slug>` que `sb refresh` sincroniza. NCBI pide
identificar la herramienta (`tool`/`email`) — se envía el nombre del
sistema y, si lo configuras, tu correo (config `pubmed.email`).
"""

from __future__ import annotations

from ..models import Document, new_id
from .base import Connector, ConnectorSpec, SyncResult
from .validated import get_json, provenance, qs

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TOOL = "segundo_cerebro"
MAX_RESULTS = 50


def search_ids(query: str, limit: int = 20, email: str | None = None, fetch=None,
               mindate: str | None = None) -> list[str]:
    url = f"{EUTILS}/esearch.fcgi?" + qs(db="pubmed", term=query, retmax=min(limit, MAX_RESULTS),
                                        retmode="json", sort="date", tool=TOOL, email=email,
                                        mindate=mindate, datetype="pdat" if mindate else None)
    data = get_json(url, fetch)
    return list(data.get("esearchresult", {}).get("idlist", []))


def fetch_summaries(pmids: list[str], email: str | None = None, fetch=None) -> list[dict]:
    if not pmids:
        return []
    url = f"{EUTILS}/esummary.fcgi?" + qs(db="pubmed", id=",".join(pmids), retmode="json",
                                          tool=TOOL, email=email)
    data = get_json(url, fetch).get("result", {})
    return [data[pid] for pid in data.get("uids", []) if isinstance(data.get(pid), dict)]


def summary_to_document(item: dict, query: str = "") -> Document | None:
    title = (item.get("title") or "").strip().rstrip(".")
    if not title:
        return None
    pmid = str(item.get("uid") or "")
    doi = next((i.get("value") for i in item.get("articleids", []) if i.get("idtype") == "doi"), None)
    pubdate = (item.get("sortpubdate") or item.get("pubdate") or "")[:10].replace("/", "-")
    year = pubdate[:4]
    date = pubdate if len(pubdate) == 10 else (f"{year}-01-01" if year.isdigit() else "1900-01-01")
    authors = ", ".join(a.get("name", "") for a in item.get("authors", [])[:8])
    journal = item.get("fulljournalname") or item.get("source") or ""
    lines = [f"# {title}", ""]
    if authors:
        lines.append(f"Autores: {authors}")
    if journal:
        lines.append(f"Revista: {journal} ({year})")
    lines.append(f"PMID: {pmid}  https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
    if doi:
        lines.append(f"DOI: https://doi.org/{doi}")
    if query:
        lines.append(f"Búsqueda guardada: {query}")
    return Document(
        id=new_id("doc"), path=f"pubmed://{pmid}", title=title[:200], doc_type="paper",
        date=date, body="\n".join(lines),
        metadata={**provenance("pubmed", pmid=pmid, doi=doi), "year": year, "journal": journal,
                  "query": query, "web_link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"},
    )


def sync(store, query: str, limit: int = 20, email: str | None = None, fetch=None,
         state: dict | None = None) -> list[Document]:
    """Trae lo nuevo de una búsqueda; con `state` recuerda los PMID vistos."""
    state = state if state is not None else {}
    seen = set(state.get("seen", []))
    ids = [i for i in search_ids(query, limit, email, fetch) if i not in seen]
    added = []
    for item in fetch_summaries(ids, email, fetch):
        doc = summary_to_document(item, query)
        if doc and store.add_document(doc):
            added.append(doc)
    state["seen"] = sorted(seen | set(ids))[-500:]
    return added


class PubMedConnector(Connector):
    spec = ConnectorSpec(
        id="pubmed", name="PubMed (búsqueda guardada)", kind="api", privacy="read-cloud",
        description="Papers con PMID/DOI desde NCBI E-utilities; solo viajan tus términos.",
        config_schema={"query": {"type": "str", "required": True, "help": "términos de búsqueda"},
                       "limit": {"type": "int", "required": False, "help": "máx. por sync (20)"},
                       "email": {"type": "str", "required": False, "help": "correo para NCBI (opcional)"}},
        setup_hint='sb literature watch "hpv self-sampling" --source pubmed')
    fetch = None   # inyectable en pruebas

    def test(self) -> dict:
        try:
            ids = search_ids(self.config["query"], 1, self.config.get("email"), type(self).fetch)
            return {"ok": True, "detail": f"PubMed responde ({len(ids)} resultado de prueba)"}
        except Exception as exc:
            return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    def sync(self, store) -> SyncResult:
        added = sync(store, self.config["query"], int(self.config.get("limit") or 20),
                     self.config.get("email"), type(self).fetch, state=self.state)
        return SyncResult(added=added)
