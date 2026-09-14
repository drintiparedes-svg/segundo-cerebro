"""Escritura mínima y reversible en TUS cuentas Google (opt-in).

Solo dos permisos, y solo si los autorizas con `sb google connect <alias>
--write`: `calendar.events` (crear/borrar eventos que el sistema creó) y
`gmail.compose` (crear/borrar borradores; NUNCA enviar). Cada operación
devuelve el id necesario para deshacerla.
"""

from __future__ import annotations

import base64
from email.mime.text import MIMEText

from .google_auth import build_service


def create_event(alias: str, summary: str, start: str, end: str, description: str = "",
                 base=None, calendar_id: str = "primary", timezone: str | None = None) -> dict:
    service = build_service("calendar", "v3", alias, base=base, write=True)
    body = {"summary": summary, "description": description,
            "start": {"dateTime": start}, "end": {"dateTime": end},
            "extendedProperties": {"private": {"segundo_cerebro": "focus_block"}}}
    if timezone:
        body["start"]["timeZone"] = timezone
        body["end"]["timeZone"] = timezone
    return service.events().insert(calendarId=calendar_id, body=body).execute()


def delete_event(alias: str, event_id: str, base=None, calendar_id: str = "primary") -> None:
    service = build_service("calendar", "v3", alias, base=base, write=True)
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()


def create_draft(alias: str, to: str, subject: str, body: str, base=None,
                 thread_id: str | None = None) -> dict:
    service = build_service("gmail", "v1", alias, base=base, write=True)
    msg = MIMEText(body, "plain", "utf-8")
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    message = {"raw": raw}
    if thread_id:
        message["threadId"] = thread_id
    return service.users().drafts().create(userId="me", body={"message": message}).execute()


def delete_draft(alias: str, draft_id: str, base=None) -> None:
    service = build_service("gmail", "v1", alias, base=base, write=True)
    service.users().drafts().delete(userId="me", id=draft_id).execute()
