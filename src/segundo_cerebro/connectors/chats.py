"""Exports de chats (WhatsApp .txt, Slack .zip) → memoria episódica.

Un Document tipo `chat` por día de conversación, con los participantes
hacia el knowledge graph. Igual que el correo: memoria local, el
contenido jamás sale del equipo.
"""

from __future__ import annotations

import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path

from ..models import Document, new_id

# «12/08/26, 14:03 - Ricardo: mensaje» (variantes con [] y segundos)
WHATSAPP_RE = re.compile(
    r"^\[?(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})[,\s]+"
    r"(\d{1,2}:\d{2})(?::\d{2})?\]?\s*[-–]?\s*([^:]{1,40}):\s(.+)$")
SYSTEM_MARKERS = ("cifrado de extremo a extremo", "end-to-end encrypted",
                  "<Multimedia omitido>", "<Media omitted>")
MAX_DAYS = 120


def _norm_year(y: str) -> str:
    return y if len(y) == 4 else f"20{y}"


def parse_whatsapp(text: str) -> dict[str, list[tuple[str, str]]]:
    """fecha ISO → [(autor, mensaje)]."""
    days: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for line in text.splitlines():
        m = WHATSAPP_RE.match(line.strip())
        if not m:
            continue
        day, month, year, _time, author, msg = m.groups()
        if any(marker in msg for marker in SYSTEM_MARKERS):
            continue
        date = f"{_norm_year(year)}-{int(month):02d}-{int(day):02d}"
        days[date].append((author.strip(), msg.strip()))
    return dict(days)


def parse_slack_zip(path: Path) -> dict[str, list[tuple[str, str]]]:
    """Export estándar de Slack: <canal>/<fecha>.json + users.json."""
    days: dict[str, list[tuple[str, str]]] = defaultdict(list)
    with zipfile.ZipFile(path) as zf:
        users = {}
        if "users.json" in zf.namelist():
            for u in json.loads(zf.read("users.json")):
                users[u.get("id")] = (u.get("profile", {}).get("real_name")
                                      or u.get("name", "?"))
        for name in zf.namelist():
            m = re.match(r"[^/]+/(\d{4}-\d{2}-\d{2})\.json$", name)
            if not m:
                continue
            for msg in json.loads(zf.read(name)):
                text = (msg.get("text") or "").strip()
                if not text or msg.get("subtype"):
                    continue
                author = users.get(msg.get("user"), msg.get("user", "?"))
                days[m.group(1)].append((author, text))
    return dict(days)


def days_to_documents(days: dict, alias: str, kind: str) -> list[Document]:
    docs = []
    for date, messages in sorted(days.items())[-MAX_DAYS:]:
        people = sorted({author for author, _ in messages})
        body_lines = [f"# {alias} — {date}", ""]
        body_lines += [f"{author}: {msg}" for author, msg in messages]
        docs.append(Document(
            id=new_id("doc"),
            path=f"{kind}://{alias}/{date}",
            title=f"{alias} · {date}",
            doc_type="chat",
            date=date,
            body="\n".join(body_lines)[:200_000],
            metadata={"source": kind, "chat": alias, "people": people,
                      "messages": len(messages)},
        ))
    return docs


def import_export(store, path: Path, alias: str | None = None) -> list[Document]:
    if not path.is_file():
        raise FileNotFoundError(f"No existe: {path}")
    name = alias or path.stem.replace("Chat de WhatsApp con ", "")
    if path.suffix.lower() == ".zip":
        days = parse_slack_zip(path)
        kind = "slack"
    elif path.suffix.lower() == ".txt":
        days = parse_whatsapp(path.read_text(encoding="utf-8", errors="replace"))
        kind = "whatsapp"
    else:
        raise ValueError("Usa el .txt exportado de WhatsApp o el .zip de Slack")
    if not days:
        raise ValueError("No encontré mensajes con formato reconocible")
    added = []
    for doc in days_to_documents(days, name, kind):
        if store.add_document(doc):
            added.append(doc)
    return added
