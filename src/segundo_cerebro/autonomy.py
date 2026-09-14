"""Matriz de autonomía: qué corre solo, qué se propone y qué nunca.

Niveles, de menor a mayor autonomía:

    L0  observar    leer y registrar
    L1  sugerir     proponer; tú decides
    L2  borrador    producto listo para tu revisión (bandeja)
    L3  automático  corre solo con registro y deshacer; nada sale del equipo
    L3+ externo     automático y reversible, en tus propias cuentas
                    (bloque en Calendar, borrador en Gmail no enviado)

Las acciones **irreversibles** (enviar, borrar, compartir, publicar, pagar)
forman la clase L4: su techo es L2 — siempre pasan por tu aprobación, y la
interfaz no permite subirlas. Con la IA apagada (`sb ai off`) todo se acota
a L2: nada corre solo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

LEVELS = ["L0", "L1", "L2", "L3", "L3+"]
LEVEL_NAMES = {"L0": "observar", "L1": "sugerir", "L2": "borrador",
               "L3": "automático interno", "L3+": "externo de bajo riesgo",
               "L4": "irreversible · siempre aprobación"}


@dataclass(frozen=True)
class Action:
    id: str
    name: str
    description: str
    default: str
    ceiling: str
    category: str            # memoria | agenda | correo | documentos | externo
    irreversible: bool = False

    @property
    def cls(self) -> str:
        return "L4" if self.irreversible else self.default


CATALOG: dict[str, Action] = {a.id: a for a in [
    Action("sync_sources", "Sincronizar fuentes", "Traer lo nuevo de carpetas, Drive, Calendar, Zotero…", "L0", "L3", "memoria"),
    Action("triage_mail", "Triaje de correo", "Priorizar la bandeja con metadatos; nunca guarda correos", "L0", "L3", "correo"),
    Action("classify_areas", "Clasificar por área", "Etiquetar documentos y compromisos con tu mapa de áreas", "L3", "L3", "memoria"),
    Action("prioritize_areas", "Priorizar áreas", "Recalcular el ranking automático (tu validación manual manda)", "L3", "L3", "memoria"),
    Action("daily_brief", "Brief diario", "Generar «Tu día» y guardarlo", "L3", "L3", "documentos"),
    Action("plan_week", "Planificar la semana", "Ubicar compromisos en los huecos libres (Carga)", "L3", "L3", "agenda"),
    Action("enrich_claude", "Enriquecer con Claude", "Segunda pasada semántica solo en áreas habilitadas", "L3", "L3", "memoria"),
    Action("weekly_review", "Revisión semanal", "Generar la revisión los lunes", "L3", "L3", "documentos"),
    Action("suggest_people", "Sugerir personas clave", "Proponer a quién fijar", "L1", "L1", "memoria"),
    Action("suggest_folders", "Sugerir carpetas", "Proponer qué conectar", "L1", "L1", "memoria"),
    Action("meeting_prep", "Preparar reuniones", "Dossier + agenda 24 h antes de cada reunión", "L2", "L3", "documentos"),
    Action("focus_block", "Bloque de foco en Calendar", "Reservar tiempo para un compromiso que vence", "L3+", "L3+", "externo"),
    Action("mail_reply_draft", "Borrador de respuesta en Gmail", "Responder a correos P1 de personas fijadas (no se envía)", "L3+", "L3+", "externo"),
    Action("send_email", "Enviar correo", "Enviar un mensaje desde tu cuenta", "L2", "L2", "externo", irreversible=True),
    Action("delete_data", "Borrar", "Eliminar archivos, eventos o correos", "L2", "L2", "externo", irreversible=True),
    Action("share_publish", "Compartir / publicar", "Dar acceso a terceros o publicar", "L2", "L2", "externo", irreversible=True),
    Action("payment", "Pagar", "Cualquier transacción", "L2", "L2", "externo", irreversible=True),
]}


def _path(brain_dir: str | Path) -> Path:
    return Path(brain_dir) / "autonomy.json"


def load_levels(brain_dir: str | Path) -> dict[str, str]:
    """Nivel efectivo configurado por acción (default + overrides válidos)."""
    levels = {a.id: a.default for a in CATALOG.values()}
    path = _path(brain_dir)
    if path.exists():
        try:
            for k, v in json.loads(path.read_text(encoding="utf-8")).items():
                if k in CATALOG and v in LEVELS and LEVELS.index(v) <= LEVELS.index(CATALOG[k].ceiling):
                    levels[k] = v
        except (json.JSONDecodeError, OSError):
            pass
    return levels


def set_level(brain_dir: str | Path, action_id: str, level: str) -> str:
    action = CATALOG.get(action_id)
    if action is None:
        raise KeyError(f"acción desconocida: {action_id}")
    if level not in LEVELS:
        raise ValueError(f"nivel inválido: {level} (usa {', '.join(LEVELS)})")
    if LEVELS.index(level) > LEVELS.index(action.ceiling):
        raise ValueError(f"«{action.name}» tiene techo {action.ceiling}"
                         + (" (irreversible: siempre aprobación)" if action.irreversible else ""))
    path = _path(brain_dir)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data[action_id] = level
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return level


def effective_level(brain_dir: str | Path, action_id: str) -> str:
    """Nivel configurado, acotado a L2 con la IA apagada (nada corre solo)."""
    from .ai import is_off
    level = load_levels(brain_dir).get(action_id, "L2")
    if is_off(brain_dir) and LEVELS.index(level) > LEVELS.index("L2"):
        return "L2"
    return level


def decide(brain_dir: str | Path, action_id: str) -> str:
    """auto · queue · suggest — qué hacer con una acción ahora."""
    level = effective_level(brain_dir, action_id)
    if level in ("L0", "L3", "L3+"):
        return "auto"
    if level == "L2":
        return "queue"
    return "suggest"


def matrix(brain_dir: str | Path) -> list[dict]:
    from .ai import is_off
    levels = load_levels(brain_dir)
    off = is_off(brain_dir)
    rows = []
    for a in CATALOG.values():
        eff = levels[a.id]
        if off and LEVELS.index(eff) > LEVELS.index("L2"):
            eff = "L2"
        rows.append({"id": a.id, "name": a.name, "description": a.description,
                     "category": a.category, "class": a.cls, "default": a.default,
                     "ceiling": a.ceiling, "level": levels[a.id], "effective": eff,
                     "irreversible": a.irreversible,
                     "options": [l for l in LEVELS if LEVELS.index(l) <= LEVELS.index(a.ceiling)]})
    return rows
