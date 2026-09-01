"""Conector Google Drive → document store.

Sincroniza contenido de texto: Google Docs (exportados como texto plano),
archivos Markdown y .txt. Presentaciones, planillas, PDFs e imágenes quedan
para una iteración posterior (requieren OCR/parsing dedicado).

Sincronización incremental: se guarda el último modifiedTime visto por
cuenta y solo se piden archivos modificados después de ese cursor.
"""

from __future__ import annotations

from ..models import Document, new_id
from .google_auth import build_service, load_state, save_state

TEXT_MIMES = {
    "application/vnd.google-apps.document": "gdoc",
    "text/markdown": "text",
    "text/plain": "text",
}
MAX_FILES_PER_SYNC = 200
MAX_BODY_CHARS = 200_000

FIELDS = "nextPageToken, files(id, name, mimeType, modifiedTime, createdTime, webViewLink, owners)"


def drive_file_to_document(meta: dict, content: str, alias: str) -> Document:
    """Función pura: metadatos de la API + contenido → Document."""
    date = (meta.get("modifiedTime") or meta.get("createdTime") or "")[:10]
    return Document(
        id=new_id("doc"),
        path=f"gdrive://{alias}/{meta['id']}",
        title=meta.get("name", "(sin título)"),
        doc_type="note",
        date=date,
        body=content[:MAX_BODY_CHARS],
        metadata={
            "source": "google-drive",
            "account": alias,
            "file_id": meta["id"],
            "mime_type": meta.get("mimeType"),
            "web_link": meta.get("webViewLink"),
            "modified_time": meta.get("modifiedTime"),
        },
    )


def _download(service, meta: dict) -> str | None:
    fid = meta["id"]
    try:
        if meta["mimeType"] == "application/vnd.google-apps.document":
            data = service.files().export(
                fileId=fid, mimeType="text/plain").execute()
        else:
            data = service.files().get_media(fileId=fid).execute()
    except Exception:
        return None  # archivo sin permiso de export o binario inesperado
    if isinstance(data, bytes):
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return str(data)


def sync(store, alias: str, query: str | None = None, base=None) -> list[Document]:
    """Sincroniza archivos de texto nuevos/modificados de la cuenta.

    `query`: filtro adicional de la API de Drive (p. ej.
    `name contains 'FALP'` o `'<folderId>' in parents`) para acotar el
    barrido a carpetas o temas específicos.
    """
    service = build_service("drive", "v3", alias, base=base)
    state = load_state(alias, base=base)
    cursor = state.get("drive_last_modified")

    mime_q = " or ".join(f"mimeType='{m}'" for m in TEXT_MIMES)
    q = f"({mime_q}) and trashed=false"
    if cursor:
        q += f" and modifiedTime > '{cursor}'"
    if query:
        q += f" and ({query})"

    files: list[dict] = []
    page_token = None
    while True:
        resp = service.files().list(
            q=q, fields=FIELDS, pageSize=100, pageToken=page_token,
            orderBy="modifiedTime",
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token or len(files) >= MAX_FILES_PER_SYNC:
            break

    added: list[Document] = []
    last_modified = cursor
    for meta in files:
        content = _download(service, meta)
        if content and content.strip():
            doc = drive_file_to_document(meta, content, alias)
            if store.add_document(doc):
                added.append(doc)
        if not last_modified or (meta.get("modifiedTime") or "") > last_modified:
            last_modified = meta.get("modifiedTime")

    if last_modified and last_modified != cursor:
        state["drive_last_modified"] = last_modified
        save_state(alias, state, base=base)
    return added
