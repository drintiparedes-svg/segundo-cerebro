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
CROSSREF = "https://api.crossref.org/works"
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


# ── validación de referencias ─────────────────────────────────────────────
# Verifica citas contra Crossref (con fallback Europe PMC) y produce un
# informe [Verificado] / [Discrepancia] / [No encontrado]. NUNCA edita el
# documento fuente. `fetch` es inyectable para testear sin red.

import difflib
import re as _re

DOI_RE = _re.compile(r"10\.\d{4,9}/[^\s\]\)\};,\"']+", _re.IGNORECASE)
YEAR_RE = _re.compile(r"\b(19|20)\d{2}\b")


def _http_fetch(url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": "segundo-cerebro/0.1 (mailto:local@user)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _norm(text: str) -> str:
    return _re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def extract_references(text: str) -> list[dict]:
    """Extrae referencias de una bibliografía: DOI cuando existe; si no,
    primer autor + año + título aproximado de entradas numeradas."""
    refs = []
    seen_dois = set()
    # entradas numeradas tipo "12. Apellido X, ... Título. Revista. 2021;..."
    for m in _re.finditer(r"^\s*(\d{1,3})[.)]\s+(.{20,400})$", text, _re.MULTILINE):
        entry = m.group(2).strip()
        doi_match = DOI_RE.search(entry)
        year_match = YEAR_RE.search(entry)
        author = entry.split(",")[0].split(" ")[0].strip()
        refs.append({
            "raw": entry[:300],
            "doi": doi_match.group(0).rstrip(".") if doi_match else None,
            "year": year_match.group(0) if year_match else None,
            "author": author if author.istitle() else None,
        })
        if doi_match:
            seen_dois.add(doi_match.group(0).rstrip(".").lower())
    # DOIs sueltos fuera de entradas numeradas
    for doi in DOI_RE.findall(text):
        doi = doi.rstrip(".")
        if doi.lower() not in seen_dois:
            seen_dois.add(doi.lower())
            refs.append({"raw": doi, "doi": doi, "year": None, "author": None})
    return refs


def verify_reference(ref: dict, fetch=_http_fetch) -> dict:
    """Veredicto: verificado | discrepancia | no_encontrado (+ detalle)."""
    try:
        if ref.get("doi"):
            data = fetch(f"{CROSSREF}/{urllib.parse.quote(ref['doi'])}")
            work = data.get("message", {})
        else:
            query = urllib.parse.quote(ref.get("raw", "")[:150])
            data = fetch(f"{CROSSREF}?query.bibliographic={query}&rows=1")
            items = data.get("message", {}).get("items", [])
            work = items[0] if items else {}
    except Exception as exc:
        return {**ref, "verdict": "no_encontrado", "detail": f"error de red: {exc}"}

    if not work:
        return {**ref, "verdict": "no_encontrado", "detail": "sin resultados"}

    found_title = " ".join(work.get("title", []) or [""])
    found_year = ""
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (work.get(key) or {}).get("date-parts", [[]])
        if parts and parts[0]:
            found_year = str(parts[0][0])
            break
    found_author = (work.get("author") or [{}])[0].get("family", "")

    issues = []
    raw_norm = _norm(ref.get("raw", ""))
    if found_title and ref.get("doi") is None:
        ratio = difflib.SequenceMatcher(
            None, _norm(found_title), raw_norm[:len(_norm(found_title)) + 40]).ratio()
        if _norm(found_title) not in raw_norm and ratio < 0.55:
            issues.append(f"título distinto ({found_title[:70]}…)")
    if ref.get("year") and found_year and ref["year"] != found_year:
        issues.append(f"año: cita {ref['year']} vs fuente {found_year}")
    if ref.get("author") and found_author and \
            _norm(ref["author"]) not in _norm(found_author) and \
            _norm(found_author) not in _norm(ref["author"]):
        issues.append(f"autor: cita {ref['author']} vs fuente {found_author}")

    verdict = "discrepancia" if issues else "verificado"
    return {**ref, "verdict": verdict, "detail": "; ".join(issues),
            "found": {"title": found_title, "year": found_year,
                      "author": found_author, "doi": work.get("DOI")}}


def verify_document(text: str, source_name: str = "",
                    fetch=_http_fetch) -> tuple[str, int, int]:
    """Verifica todas las referencias y devuelve (informe_md, ok, total)."""
    refs = extract_references(text)
    labels = {"verificado": "[Verificado]", "discrepancia": "[Discrepancia]",
              "no_encontrado": "[No encontrado]"}
    lines = [f"# Verificación de referencias — {source_name}", ""]
    ok = 0
    for ref in refs:
        result = verify_reference(ref, fetch=fetch)
        if result["verdict"] == "verificado":
            ok += 1
        detail = f" — {result['detail']}" if result.get("detail") else ""
        lines.append(f"- {labels[result['verdict']]} {ref['raw'][:140]}{detail}")
    lines += ["",
              f"**Resultado: {ok}/{len(refs)} verificadas.** "
              "Fuente consultada: Crossref. El documento original no fue "
              "modificado; corrige a partir de este informe."]
    return "\n".join(lines), ok, len(refs)
