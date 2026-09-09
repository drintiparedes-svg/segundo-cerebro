"""Conector de literatura abierta → memoria semántica.

Consulta Europe PMC (REST público, sin API key): metadatos, abstract,
DOI y estado open access de artículos científicos. Cada artículo entra
como Document tipo `paper`; el resto del pipeline (áreas, búsqueda,
context engine) lo trata como cualquier otra fuente.

Solo lectura y solo metadatos públicos: nada personal viaja en la
consulta más allá de los términos de búsqueda que tú eliges.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from ..models import Document, new_id

EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
MAX_RESULTS = 50


def result_to_document(item: dict) -> Document | None:
    """Convierte un resultado de Europe PMC en Document. Función pura."""
    title = (item.get("title") or "").strip().rstrip(".")
    if not title:
        return None
    year = str(item.get("pubYear") or "")
    date = f"{year}-01-01" if year.isdigit() else "1900-01-01"

    lines = [f"# {title}", ""]
    if item.get("authorString"):
        lines.append(f"Autores: {item['authorString']}")
    journal = (item.get("journalInfo", {}).get("journal", {}) or {}).get("title") \
        or item.get("journalTitle") or ""
    if journal:
        lines.append(f"Revista: {journal} ({year})")
    if item.get("doi"):
        lines.append(f"DOI: https://doi.org/{item['doi']}")
    if item.get("abstractText"):
        lines += ["", "## Abstract", item["abstractText"]]

    return Document(
        id=new_id("doc"),
        path=f"europepmc://{item.get('source', 'MED')}/{item.get('id', '')}",
        title=title[:200],
        doc_type="paper",
        date=date,
        body="\n".join(lines),
        metadata={
            "source": "europepmc",
            "doi": item.get("doi"),
            "year": year,
            "journal": journal,
            "open_access": item.get("isOpenAccess") == "Y",
            "pmid": item.get("pmid"),
        },
    )


def search(query: str, limit: int = 15, open_only: bool = False,
           timeout: int = 30) -> list[dict]:
    q = f"(OPEN_ACCESS:y) AND ({query})" if open_only else query
    params = urllib.parse.urlencode({
        "query": q, "format": "json", "resultType": "core",
        "pageSize": min(limit, MAX_RESULTS),
    })
    req = urllib.request.Request(
        f"{EUROPE_PMC}?{params}",
        headers={"User-Agent": "segundo-cerebro/0.1 (personal knowledge tool)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("resultList", {}).get("result", [])


def sync(store, query: str, limit: int = 15, open_only: bool = False) -> list[Document]:
    """Busca y guarda artículos nuevos (deduplicados por contenido)."""
    added = []
    for item in search(query, limit=limit, open_only=open_only):
        doc = result_to_document(item)
        if doc and store.add_document(doc):
            added.append(doc)
    return added
