"""Autenticación Google multi-cuenta (OAuth instalado, mínimo privilegio).

Distribución de archivos (todo bajo .brain/google/, fuera de git):

    .brain/google/client_secret.json   ← credencial OAuth de TU proyecto GCP
    .brain/google/token-<alias>.json   ← token por cuenta Gmail autorizada
    .brain/google/state-<alias>.json   ← cursores de sincronización

Un alias por correo: `sb google connect personal`, `sb google connect falp`…
Cada `connect` abre el navegador para autorizar ESA cuenta; el refresh token
queda guardado y las sincronizaciones siguientes no piden nada.

Scopes de solo lectura: este sistema observa; jamás modifica tu Drive,
Calendar o Gmail. Cuentas autorizadas antes de añadir Gmail deben
re-autorizarse una vez (sb google connect <alias>) para otorgar el
nuevo permiso de lectura.
"""

from __future__ import annotations

import json
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]

DEFAULT_GOOGLE_DIR = Path(".brain/google")


class GoogleAuthError(RuntimeError):
    pass


def google_dir(base: str | Path | None = None) -> Path:
    d = Path(base) if base else DEFAULT_GOOGLE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_accounts(base: str | Path | None = None) -> list[str]:
    """Aliases de cuentas ya autorizadas (token-<alias>.json presentes)."""
    return sorted(
        p.stem.removeprefix("token-")
        for p in google_dir(base).glob("token-*.json")
    )


def get_credentials(alias: str, base: str | Path | None = None,
                    interactive: bool = False):
    """Credenciales para una cuenta. Con interactive=True lanza el flujo
    OAuth en el navegador (primera vez por cuenta)."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise GoogleAuthError(
            "Faltan dependencias de Google. Instala con: pip install -e '.[google]'"
        ) from exc

    gdir = google_dir(base)
    token_path = gdir / f"token-{alias}.json"
    secret_path = gdir / "client_secret.json"

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())

    if not creds or not creds.valid:
        if not interactive:
            raise GoogleAuthError(
                f"La cuenta «{alias}» no está autorizada. "
                f"Ejecuta: sb google connect {alias}"
            )
        if not secret_path.exists():
            raise GoogleAuthError(
                f"No existe {secret_path}. Crea una credencial OAuth "
                "(Desktop app) en Google Cloud Console y guárdala ahí. "
                "Guía: docs/07-conectores-google.md"
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
        # Abre el navegador; sirve para autorizar cualquiera de tus Gmail.
        creds = flow.run_local_server(port=0, prompt="consent")
        token_path.write_text(creds.to_json())

    return creds


def build_service(api: str, version: str, alias: str,
                  base: str | Path | None = None):
    from googleapiclient.discovery import build

    creds = get_credentials(alias, base=base)
    return build(api, version, credentials=creds, cache_discovery=False)


# ── estado de sincronización por cuenta ────────────────────────────────────

def load_state(alias: str, base: str | Path | None = None) -> dict:
    path = google_dir(base) / f"state-{alias}.json"
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_state(alias: str, state: dict, base: str | Path | None = None) -> None:
    path = google_dir(base) / f"state-{alias}.json"
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2))
