"""Conector Google Drive → document store.

Sincroniza: Google Docs y Google Sheets (exportados como texto/CSV),
Markdown/txt, y binarios Office y PDF (.docx .xlsx .pptx .pdf, parseados
con los mismos lectores del conector local — extra [files]). Imágenes y
videos quedan fuera.

Sincronización incremental: se guarda el último modifiedTime visto por
cuenta y solo se piden archivos modificados después de ese cursor.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ..models import Document, new_id
from .google_auth import build_service, load_state, save_state
from .localfs import read_file_text

EXPORT_MIMES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
}
BINARY_MIMES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/pdf": ".pdf",
}
TEXT_MIMES = {
    **{m: "export" for m in EXPORT_MIMES},
    **{m: "binary" for m in BINARY_MIMES},
    "text/markdown": "text",
    "text/plain": "text",
    "text/csv": "text",
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
    fid, mime = meta["id"], meta["mimeType"]
    try:
        if mime in EXPORT_MIMES:
            data = service.files().export(
                fileId=fid, mimeType=EXPORT_MIMES[mime]).execute()
        else:
            data = service.files().get_media(fileId=fid).execute()
    except Exception:
        return None  # archivo sin permiso de export o inesperado

    if mime in BINARY_MIMES:
        # Reutiliza los lectores del conector local (docx/xlsx/pptx/pdf)
        # a través de un archivo temporal que se elimina de inmediato.
        if not isinstance(data, bytes):
            return None
        suffix = BINARY_MIMES[mime]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            return read_file_text(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    if isinstance(data, bytes):
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return str(data)


def list_root_folders(alias: str, base=None, limit: int = 200) -> list[dict]:
    """Carpetas de primer nivel de «Mi unidad» (solo id y nombre) para
    elegir cuáles seguir en `sb google suggest`."""
    service = build_service("drive", "v3", alias, base=base)
    resp = service.files().list(
        q="mimeType='application/vnd.google-apps.folder' and trashed=false "
          "and 'root' in parents",
        fields="files(id,name,modifiedTime)", pageSize=limit, orderBy="name",
    ).execute()
    return [{"id": f["id"], "name": f["name"],
             "modified_time": f.get("modifiedTime")} for f in resp.get("files", [])]


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
    folders = state.get("drive_folders") or []
    if folders and not query:
        parents = " or ".join(f"'{f['id']}' in parents" for f in folders)
        q += f" and ({parents})"

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
