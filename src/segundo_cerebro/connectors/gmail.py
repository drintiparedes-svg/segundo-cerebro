"""Conector Gmail — SOLO LECTURA, pensado para triaje de bandeja.

Reglas de privacidad (ver docs/10-agentes-y-privacidad.md):
- Scope `gmail.readonly`: este sistema no puede enviar, borrar ni marcar
  correos. Solo observa.
- Los correos NO se guardan en la memoria del cerebro: se leen, se
  priorizan y se descartan. El único rastro es el informe local en
  .brain/reports/ (fuera de git).
- Por defecto se trae solo metadatos + snippet; el cuerpo completo es
  opt-in explícito (include_bodies=True).
"""

from __future__ import annotations

import base64
import re
from email.utils import parsedate_to_datetime

from .google_auth import GoogleAuthError, build_service

DEFAULT_QUERY = "in:inbox newer_than:{days}d"
MAX_MESSAGES = 200


def message_to_email(msg: dict, alias: str, body: str | None = None) -> dict:
    """Convierte la respuesta de la API en un dict plano. Función pura."""
    headers = {
        h["name"].lower(): h["value"]
        for h in msg.get("payload", {}).get("headers", [])
    }
    date_iso = ""
    if headers.get("date"):
        try:
            date_iso = parsedate_to_datetime(headers["date"]).isoformat()
        except (TypeError, ValueError):
            pass
    return {
        "id": msg.get("id", ""),
        "account": alias,
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", "(sin asunto)"),
        "date": date_iso,
        "snippet": msg.get("snippet", ""),
        "labels": msg.get("labelIds", []),
        "body": body or "",
    }


def extract_body(payload: dict) -> str:
    """Extrae el texto plano del cuerpo (recorre las partes MIME)."""
    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data")
        if data:
            return base64.urlsafe_b64decode(data + "===").decode("utf-8", "replace")
    for part in payload.get("parts", []) or []:
        text = extract_body(part)
        if text:
            return text
    return ""


def sender_name(from_header: str) -> str:
    """«Ricardo Morales <r@falp.org>» → «Ricardo Morales»."""
    m = re.match(r'^"?([^"<]+?)"?\s*<', from_header)
    return (m.group(1) if m else from_header.split("@")[0]).strip()


def fetch_inbox(alias: str, days: int = 7, query: str | None = None,
                include_bodies: bool = False, limit: int = 50,
                base=None) -> list[dict]:
    """Trae los correos recientes de la cuenta. Solo lectura."""
    limit = min(limit, MAX_MESSAGES)
    service = build_service("gmail", "v1", alias, base=base)
    q = query or DEFAULT_QUERY.format(days=days)
    try:
        listing = service.users().messages().list(
            userId="me", q=q, maxResults=limit).execute()
    except Exception as exc:
        if "insufficient" in str(exc).lower() or "403" in str(exc):
            raise GoogleAuthError(
                f"La cuenta «{alias}» no tiene el permiso de lectura de Gmail. "
                f"Vuelve a autorizarla: sb google connect {alias}"
            ) from exc
        raise

    emails: list[dict] = []
    for ref in listing.get("messages", []):
        if include_bodies:
            msg = service.users().messages().get(
                userId="me", id=ref["id"], format="full").execute()
            body = extract_body(msg.get("payload", {}))[:20_000]
        else:
            msg = service.users().messages().get(
                userId="me", id=ref["id"], format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"]).execute()
            body = ""
        emails.append(message_to_email(msg, alias, body=body))
    return emails
