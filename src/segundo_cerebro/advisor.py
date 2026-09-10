"""Asesor de fuentes: qué carpetas de tu equipo conviene conectar.

Recorre (SOLO LECTURA, sin abrir ningún archivo — solo nombres, tamaños y
fechas) el escritorio y las carpetas estándar, y puntúa cada subcarpeta
según cuántos archivos soportados tiene, cuán reciente es su actividad y
cuánto calza con tu mapa de áreas. La decisión final es tuya: aceptas o
ignoras una a una; ambas se recuerdan en .brain/sources.json.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from .areas import Area
from .connectors.localfs import (OPTIONAL_EXTS, SKIP_DIRS, TEXT_EXTS,
                                 add_source, load_registry, save_registry)
from .models import now_iso

SUPPORTED = TEXT_EXTS | OPTIONAL_EXTS
NOISE_DIRS = SKIP_DIRS | {"Library", "AppData", "Applications", ".cache",
                          "venv", "env", "dist", "build", "target"}
STANDARD_FOLDERS = ["Documents", "Documentos", "Downloads", "Descargas",
                    "OneDrive", "OneDrive - FALP", "Google Drive", "Mi unidad",
                    "Dropbox", "iCloud Drive"]
TOKEN_RE = re.compile(r"[a-záéíóúñü0-9]+", re.IGNORECASE)


def candidate_roots(desktop: Path | None = None, home: Path | None = None) -> list[Path]:
    """Escritorio + carpetas estándar que existan (sin duplicados)."""
    home = home or Path.home()
    roots: list[Path] = []
    if desktop and desktop.is_dir():
        roots.append(desktop)
    for name in STANDARD_FOLDERS:
        p = home / name
        if p.is_dir() and p not in roots:
            roots.append(p)
    return roots


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in TOKEN_RE.findall(text) if len(t) > 2}


def _area_vocab(areas: list[Area]) -> dict[str, set[str]]:
    vocab = {}
    for a in areas:
        words = set()
        for w in a.keywords + a.projects + a.people + [a.name]:
            words |= _tokens(w)
        vocab[a.id] = words
    return vocab


def scan_folder(folder: Path, areas: list[Area] | None = None,
                recent_days: int = 90, max_files: int = 5000,
                max_depth: int = 4, now: float | None = None) -> dict:
    """Estadísticas de una carpeta sin abrir archivos. Se detiene en
    `max_files` para que Descargas gigantes no cuelguen el asesor."""
    now = now or time.time()
    cutoff = now - recent_days * 86_400
    vocab = _area_vocab(areas or [])
    stats = {"total": 0, "supported": 0, "recent": 0, "bytes": 0,
             "types": {}, "truncated": False}
    hits: dict[str, int] = {}
    name_tokens = _tokens(folder.name)

    def walk(path: Path, depth: int):
        if stats["total"] >= max_files:
            stats["truncated"] = True
            return
        try:
            entries = list(os.scandir(path))
        except (PermissionError, OSError):
            return
        for entry in entries:
            if stats["total"] >= max_files:
                stats["truncated"] = True
                return
            name = entry.name
            if name.startswith(".") or name.startswith("~$"):
                continue
            if entry.is_dir(follow_symlinks=False):
                if name in NOISE_DIRS or depth >= max_depth:
                    continue
                walk(Path(entry.path), depth + 1)
                continue
            if not entry.is_file(follow_symlinks=False):
                continue
            stats["total"] += 1
            ext = os.path.splitext(name)[1].lower()
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if ext in SUPPORTED:
                stats["supported"] += 1
                stats["bytes"] += st.st_size
                stats["types"][ext] = stats["types"].get(ext, 0) + 1
                if st.st_mtime >= cutoff:
                    stats["recent"] += 1
                toks = _tokens(os.path.splitext(name)[0])
                for aid, words in vocab.items():
                    if toks & words:
                        hits[aid] = hits.get(aid, 0) + 1

    walk(folder, 0)
    for aid, words in vocab.items():
        if name_tokens & words:
            hits[aid] = hits.get(aid, 0) + 5   # el nombre de la carpeta pesa
    area_guess = max(hits, key=hits.get) if hits else None
    return {**stats, "area_hits": hits, "area_guess": area_guess}


def score_folder(stats: dict) -> tuple[int, str, list[str]]:
    """(score, veredicto, razones). Veredicto: conectar · revisar · ignorar."""
    reasons = []
    supported, recent, total = stats["supported"], stats["recent"], stats["total"]
    if supported == 0:
        return 0, "ignorar", ["sin archivos de texto/oficina soportados"]
    score = min(40, supported) + min(30, recent * 3)
    reasons.append(f"{supported} archivos soportados")
    if recent:
        reasons.append(f"{recent} modificados en los últimos 90 días")
    if stats.get("area_guess"):
        score += min(30, stats["area_hits"][stats["area_guess"]] * 5)
        reasons.append(f"calza con el área «{stats['area_guess']}»")
    if total and supported / total < 0.05 and supported < 5:
        return score, "ignorar", reasons + ["casi todo son binarios/fotos/instaladores"]
    if supported >= 5 and (recent or stats.get("area_guess")):
        return score, "conectar", reasons
    return score, "revisar", reasons + ["pocas señales; decide tú"]


def suggest_sources(brain_dir: str | Path, roots: list[Path],
                    areas: list[Area] | None = None, **scan_kwargs) -> list[dict]:
    """Sugerencias para las subcarpetas de cada raíz, sin las ya registradas
    ni las ignoradas antes. Ordenadas por score."""
    registry = load_registry(brain_dir)
    known = {s["path"] for s in registry["sources"]} | set(registry.get("ignored", []))
    out = []
    for root in roots:
        try:
            children = sorted(p for p in root.iterdir()
                              if p.is_dir() and not p.name.startswith("."))
        except OSError:
            continue
        for child in children:
            path = str(child.resolve())
            if path in known or child.name in NOISE_DIRS:
                continue
            stats = scan_folder(child, areas, **scan_kwargs)
            score, verdict, reasons = score_folder(stats)
            out.append({"path": path, "name": child.name, "root": str(root),
                        "score": score, "verdict": verdict, "reasons": reasons,
                        "files": stats["supported"], "recent": stats["recent"],
                        "area_guess": stats["area_guess"], "types": stats["types"]})
    order = {"conectar": 0, "revisar": 1, "ignorar": 2}
    out.sort(key=lambda s: (order[s["verdict"]], -s["score"], s["name"].lower()))
    registry["suggested_at"] = now_iso()
    save_registry(brain_dir, registry)
    return out


def apply_suggestion(brain_dir: str | Path, path: str | Path, accept: bool) -> dict:
    """Acepta (registra como fuente de solo lectura) o ignora una carpeta."""
    if accept:
        return {"path": str(path), "action": "conectada",
                **add_source(brain_dir, path)}
    registry = load_registry(brain_dir)
    resolved = str(Path(path).expanduser().resolve())
    ignored = registry.setdefault("ignored", [])
    if resolved not in ignored:
        ignored.append(resolved)
    save_registry(brain_dir, registry)
    return {"path": resolved, "action": "ignorada"}


def drive_query_suggestions(areas: list[Area]) -> list[dict]:
    """Filtros de Drive por área, a partir de proyectos y palabras clave
    (solo se envían los términos, nunca contenido)."""
    out = []
    for a in areas:
        terms = [t for t in (a.projects + a.keywords[:4]) if len(t) > 3][:5]
        if terms:
            q = " or ".join(f"name contains '{t}'" for t in terms)
            out.append({"area": a.id, "name": a.name, "query": q})
    return out
