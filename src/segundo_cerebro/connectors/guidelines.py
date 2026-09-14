"""Guías y alertas por RSS/Atom (WHO, MINSAL, sociedades científicas…).

Cada feed es una instancia `guidelines:<slug>` con su URL; cada entrada
entra como documento `guideline` con enlace y fecha de publicación.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

from ..models import Document, new_id
from .base import Connector, ConnectorSpec, SyncResult
from .validated import get_text, provenance

ATOM = "{http://www.w3.org/2005/Atom}"
TAG_RE = re.compile(r"<[^>]+>")


def _date(text: str | None) -> str:
    if not text:
        return "1900-01-01"
    try:
        return parsedate_to_datetime(text).date().isoformat()
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10] if re.match(r"\d{4}-\d{2}-\d{2}", text) else "1900-01-01"


def parse_feed(xml_text: str) -> list[dict]:
    """RSS 2.0 y Atom → [{title, link, date, summary, id}]."""
    root = ET.fromstring(xml_text.strip())
    items = []
    for it in root.iter("item"):                       # RSS
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "date": _date(it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date")),
            "summary": TAG_RE.sub("", it.findtext("description") or "").strip()[:2000],
            "id": (it.findtext("guid") or it.findtext("link") or "").strip(),
        })
    for e in root.iter(f"{ATOM}entry"):                # Atom
        link_el = e.find(f"{ATOM}link")
        link = (link_el.get("href") if link_el is not None else "") or ""
        items.append({
            "title": (e.findtext(f"{ATOM}title") or "").strip(),
            "link": link.strip(),
            "date": _date(e.findtext(f"{ATOM}updated") or e.findtext(f"{ATOM}published")),
            "summary": TAG_RE.sub("", e.findtext(f"{ATOM}summary") or e.findtext(f"{ATOM}content") or "").strip()[:2000],
            "id": (e.findtext(f"{ATOM}id") or link).strip(),
        })
    return [i for i in items if i["title"]]


def entry_to_document(entry: dict, feed_name: str) -> Document:
    lines = [f"# {entry['title']}", "", f"Fuente: {feed_name}", f"Enlace: {entry['link']}",
             f"Publicado: {entry['date']}"]
    if entry.get("summary"):
        lines += ["", entry["summary"]]
    return Document(
        id=new_id("doc"), path=entry["link"] or f"guideline://{feed_name}/{entry['id']}",
        title=entry["title"][:200], doc_type="guideline", date=entry["date"], body="\n".join(lines),
        metadata={**provenance("guidelines", url=entry["link"]), "feed": feed_name,
                  "entry_id": entry["id"], "web_link": entry["link"]},
    )


def sync(store, url: str, name: str, fetch=None, state: dict | None = None, limit: int = 30) -> list[Document]:
    state = state if state is not None else {}
    seen = set(state.get("seen", []))
    added = []
    for entry in parse_feed(get_text(url, fetch))[:limit]:
        if entry["id"] in seen:
            continue
        seen.add(entry["id"])
        doc = entry_to_document(entry, name)
        if store.add_document(doc):
            added.append(doc)
    state["seen"] = sorted(seen)[-1000:]
    return added


class GuidelinesConnector(Connector):
    spec = ConnectorSpec(
        id="guidelines", name="Guías / alertas (RSS)", kind="api", privacy="read-cloud",
        description="Feed RSS/Atom de una fuente oficial (WHO, MINSAL, sociedad científica).",
        config_schema={"url": {"type": "str", "required": True, "help": "URL del feed"},
                       "name": {"type": "str", "required": False, "help": "nombre de la fuente"}},
        setup_hint="sb connect add guidelines --config url=https://www.who.int/rss-feeds/news-english.xml --config name=WHO")
    fetch = None

    @property
    def label(self) -> str:
        return self.config.get("name") or self.config.get("url", self.id)

    def test(self) -> dict:
        try:
            n = len(parse_feed(get_text(self.config["url"], type(self).fetch)))
            return {"ok": n > 0, "detail": f"{n} entradas en el feed"}
        except Exception as exc:
            return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    def sync(self, store) -> SyncResult:
        added = sync(store, self.config["url"], self.label, type(self).fetch, state=self.state)
        return SyncResult(added=added)
