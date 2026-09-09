"""Conector Zotero: biblioteca de referencias → memoria (tipo paper).

Lee exports estándar de Zotero — BibTeX (.bib) o CSL-JSON (.json) — con
parsers propios sin dependencias. Cada entrada se guarda con el mismo
formato que los papers de Europe PMC, así la validación de literatura y
el Writing agent los tratan igual. Todo local: solo se lee el archivo
que tú exportas.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..models import Document, new_id

ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,]+),", re.MULTILINE)
FIELD_RE = re.compile(
    r"(\w+)\s*=\s*(?:\{((?:[^{}]|\{[^{}]*\})*)\}|\"([^\"]*)\")", re.DOTALL)


def parse_bibtex(text: str) -> list[dict]:
    """Parser ligero de BibTeX: entradas @tipo{clave, campo={...}}."""
    entries = []
    for match in ENTRY_RE.finditer(text):
        start = match.end()
        # el bloque termina donde empieza la siguiente entrada (o EOF)
        nxt = ENTRY_RE.search(text, start)
        block = text[start:nxt.start() if nxt else len(text)]
        fields = {}
        for fm in FIELD_RE.finditer(block):
            value = (fm.group(2) or fm.group(3) or "").strip()
            fields[fm.group(1).lower()] = re.sub(r"\s+", " ", value)
        entries.append({"type": match.group(1).lower(),
                        "key": match.group(2).strip(), **fields})
    return entries


def parse_csl_json(text: str) -> list[dict]:
    """CSL-JSON (export por defecto de Zotero → 'Better CSL JSON')."""
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("CSL-JSON debe ser una lista de referencias")
    entries = []
    for item in data:
        authors = ", ".join(
            " ".join(filter(None, [a.get("given"), a.get("family")]))
            for a in item.get("author", []))
        year = ""
        issued = item.get("issued", {}).get("date-parts", [[]])
        if issued and issued[0]:
            year = str(issued[0][0])
        entries.append({
            "type": item.get("type", "article"),
            "key": item.get("id", ""),
            "title": item.get("title", ""),
            "author": authors,
            "year": year,
            "journal": item.get("container-title", ""),
            "doi": item.get("DOI", ""),
        })
    return entries


def entry_to_document(entry: dict) -> Document | None:
    title = re.sub(r"[{}]", "", entry.get("title", "")).strip().rstrip(".")
    if not title:
        return None
    year = entry.get("year", "") or ""
    year = re.search(r"\d{4}", year).group(0) if re.search(r"\d{4}", year) else ""
    journal = entry.get("journal") or entry.get("journaltitle") or \
        entry.get("booktitle") or ""
    doi = (entry.get("doi") or "").replace("https://doi.org/", "")

    lines = [f"# {title}", ""]
    if entry.get("author"):
        lines.append(f"Autores: {entry['author']}")
    if journal:
        lines.append(f"Revista: {journal} ({year})")
    if doi:
        lines.append(f"DOI: https://doi.org/{doi}")
    if entry.get("abstract"):
        lines += ["", "## Abstract", entry["abstract"]]

    return Document(
        id=new_id("doc"),
        path=f"zotero://{entry.get('key', title[:40])}",
        title=title[:200],
        doc_type="paper",
        date=f"{year}-01-01" if year else "1900-01-01",
        body="\n".join(lines),
        metadata={"source": "zotero", "doi": doi or None, "year": year,
                  "journal": journal, "entry_type": entry.get("type")},
    )


def import_library(store, path: Path) -> list[Document]:
    if not path.is_file():
        raise FileNotFoundError(f"No existe: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        entries = parse_csl_json(text)
    elif path.suffix.lower() == ".bib":
        entries = parse_bibtex(text)
    else:
        raise ValueError("Formato no soportado: usa export .bib o CSL-JSON de Zotero")
    added = []
    for entry in entries:
        doc = entry_to_document(entry)
        if doc and store.add_document(doc):
            added.append(doc)
    return added
