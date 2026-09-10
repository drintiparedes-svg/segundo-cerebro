"""Conector Google Calendar → memoria episódica.

Cada evento del calendario se convierte en un Document tipo `meeting`
(si tiene invitados) o `note`; el extractor genera el KO `event` y las
relaciones persona—proyecto. Los asistentes alimentan el knowledge graph.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import Document, new_id
from .google_auth import build_service, load_state

MAX_EVENTS = 500


def event_to_document(event: dict, alias: str) -> Document | None:
    """Convierte un evento de la API de Calendar en un Document.

    Función pura (testeable sin red). Devuelve None para eventos sin título
    o cancelados.
    """
    if event.get("status") == "cancelled":
        return None
    title = (event.get("summary") or "").strip()
    if not title:
        return None

    start = event.get("start", {})
    date = (start.get("date") or start.get("dateTime") or "")[:10]
    if not date:
        return None

    attendees = [
        a.get("displayName") or a.get("email", "").split("@")[0]
        for a in event.get("attendees", [])
        if not a.get("resource") and not a.get("self")
    ]
    organizer = event.get("organizer", {})
    organizer_name = organizer.get("displayName") or organizer.get("email", "")

    lines = [f"# {title}", ""]
    if start.get("dateTime"):
        lines.append(f"Inicio: {start['dateTime']}")
    if attendees:
        lines.append(f"Asistentes: {', '.join(attendees)}")
    if organizer_name:
        lines.append(f"Organiza: {organizer_name}")
    if event.get("location"):
        lines.append(f"Lugar: {event['location']}")
    if event.get("description"):
        lines += ["", event["description"]]

    return Document(
        id=new_id("doc"),
        path=f"gcal://{alias}/{event.get('id', '')}",
        title=title,
        doc_type="meeting" if attendees else "note",
        date=date,
        body="\n".join(lines),
        metadata={
            "source": "google-calendar",
            "account": alias,
            "people": attendees,
            "event_id": event.get("id"),
            "html_link": event.get("htmlLink"),
        },
    )


def list_calendars(alias: str, base=None) -> list[dict]:
    """Calendarios visibles de la cuenta (solo id, nombre y rol)."""
    service = build_service("calendar", "v3", alias, base=base)
    resp = service.calendarList().list(maxResults=100).execute()
    return [{"id": c["id"], "name": c.get("summary", c["id"]),
             "primary": bool(c.get("primary")),
             "role": c.get("accessRole", "")}
            for c in resp.get("items", [])]


def chosen_calendars(alias: str, base=None) -> list[str]:
    """Calendarios a sincronizar: los elegidos en `sb google suggest`, o
    `primary` si nunca se eligió nada."""
    return load_state(alias, base=base).get("calendars") or ["primary"]


def fetch_events(alias: str, days_back: int = 30, days_forward: int = 30,
                 base=None, calendars: list[str] | None = None) -> list[dict]:
    service = build_service("calendar", "v3", alias, base=base)
    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=days_back)).isoformat()
    time_max = (now + timedelta(days=days_forward)).isoformat()

    events: list[dict] = []
    for calendar_id in calendars or chosen_calendars(alias, base=base):
        page_token = None
        while True:
            resp = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min, timeMax=time_max,
                singleEvents=True, orderBy="startTime",
                maxResults=250, pageToken=page_token,
            ).execute()
            events.extend(resp.get("items", []))
            page_token = resp.get("nextPageToken")
            if not page_token or len(events) >= MAX_EVENTS:
                break
    return events


def sync(store, alias: str, days_back: int = 30, days_forward: int = 30,
         base=None) -> list[Document]:
    """Trae eventos y devuelve los Documents NUEVOS ya insertados en la
    memoria (la deduplicación por hash hace la operación idempotente)."""
    added = []
    for event in fetch_events(alias, days_back, days_forward, base=base):
        doc = event_to_document(event, alias)
        if doc and store.add_document(doc):
            added.append(doc)
    return added
