"""ClinicalTrials.gov (API v2 oficial) → ensayos con NCT, estado y fase."""

from __future__ import annotations

from ..models import Document, new_id
from .base import Connector, ConnectorSpec, SyncResult
from .validated import get_json, provenance, qs

API = "https://clinicaltrials.gov/api/v2/studies"
MAX_RESULTS = 50


def search(query: str, limit: int = 20, fetch=None, status: str | None = None) -> list[dict]:
    url = f"{API}?" + qs(**{"query.term": query, "pageSize": min(limit, MAX_RESULTS),
                            "filter.overallStatus": status, "format": "json"})
    return list(get_json(url, fetch).get("studies", []))


def study_to_document(study: dict, query: str = "") -> Document | None:
    proto = study.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    status = proto.get("statusModule", {})
    design = proto.get("designModule", {})
    cond = proto.get("conditionsModule", {})
    desc = proto.get("descriptionModule", {})
    nct = ident.get("nctId")
    title = (ident.get("officialTitle") or ident.get("briefTitle") or "").strip()
    if not nct or not title:
        return None
    start = (status.get("startDateStruct") or {}).get("date") or ""
    date = start if len(start) == 10 else (f"{start}-01" if len(start) == 7 else "1900-01-01")
    phases = ", ".join(design.get("phases", []) or [])
    lines = [f"# {title}", "", f"NCT: {nct}  https://clinicaltrials.gov/study/{nct}",
             f"Estado: {status.get('overallStatus', '')}" + (f" · Fase: {phases}" if phases else "")]
    if cond.get("conditions"):
        lines.append("Condiciones: " + ", ".join(cond["conditions"][:6]))
    if desc.get("briefSummary"):
        lines += ["", "## Resumen", desc["briefSummary"]]
    if query:
        lines.append(f"\nBúsqueda guardada: {query}")
    return Document(
        id=new_id("doc"), path=f"clinicaltrials://{nct}", title=title[:200], doc_type="trial",
        date=date, body="\n".join(lines),
        metadata={**provenance("clinicaltrials", nct=nct), "status": status.get("overallStatus"),
                  "phases": phases, "conditions": cond.get("conditions", [])[:6], "query": query,
                  "web_link": f"https://clinicaltrials.gov/study/{nct}"},
    )


def sync(store, query: str, limit: int = 20, fetch=None, state: dict | None = None,
         status: str | None = None) -> list[Document]:
    state = state if state is not None else {}
    seen = set(state.get("seen", []))
    added = []
    for study in search(query, limit, fetch, status):
        doc = study_to_document(study, query)
        if doc is None or doc.metadata["nct"] in seen:
            continue
        seen.add(doc.metadata["nct"])
        if store.add_document(doc):
            added.append(doc)
    state["seen"] = sorted(seen)[-500:]
    return added


class ClinicalTrialsConnector(Connector):
    spec = ConnectorSpec(
        id="clinicaltrials", name="ClinicalTrials.gov (búsqueda guardada)", kind="api", privacy="read-cloud",
        description="Ensayos clínicos con NCT, estado y fase; solo viajan tus términos.",
        config_schema={"query": {"type": "str", "required": True, "help": "términos"},
                       "status": {"type": "str", "required": False, "help": "RECRUITING, COMPLETED…"}},
        setup_hint='sb literature watch "HPV self-sampling" --source clinicaltrials')
    fetch = None

    def test(self) -> dict:
        try:
            n = len(search(self.config["query"], 1, type(self).fetch))
            return {"ok": True, "detail": f"ClinicalTrials.gov responde ({n} de prueba)"}
        except Exception as exc:
            return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    def sync(self, store) -> SyncResult:
        added = sync(store, self.config["query"], 20, type(self).fetch, state=self.state,
                     status=self.config.get("status"))
        return SyncResult(added=added)
