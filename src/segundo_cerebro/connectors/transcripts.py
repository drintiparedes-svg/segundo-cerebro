"""Transcripciones de reuniones: detección de hablantes y limpieza.

Soporta texto plano con patrón «Nombre: dicho» y subtítulos .vtt/.srt.
El resultado alimenta la memoria episódica: la transcripción entra como
reunión (doc_type meeting) con sus participantes hacia el grafo.
"""

from __future__ import annotations

import re

SPEAKER_RE = re.compile(r"^([A-ZÁÉÍÓÚÑ][\w .áéíóúñÁÉÍÓÚÑ-]{1,40}?)\s*:\s+(.+)$")
VTT_TS_RE = re.compile(r"^\d{2}:\d{2}(?::\d{2})?[.,]\d{3}\s*-->")
SRT_INDEX_RE = re.compile(r"^\d+$")
MIN_SPEAKER_LINES = 3


def strip_captions(text: str) -> str:
    """Quita cabeceras WEBVTT, índices SRT y timestamps; conserva el habla."""
    lines = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean or clean == "WEBVTT" or SRT_INDEX_RE.match(clean) \
                or VTT_TS_RE.match(clean):
            continue
        lines.append(clean)
    return "\n".join(lines)


def parse_transcript(text: str) -> tuple[list[str], str]:
    """Devuelve (participantes, texto limpio). Participantes = hablantes
    con al menos una intervención con el patrón «Nombre: …»."""
    clean = strip_captions(text)
    speakers: dict[str, int] = {}
    for line in clean.splitlines():
        m = SPEAKER_RE.match(line)
        if m:
            name = m.group(1).strip()
            if name.upper() not in ("DECISIÓN", "DECISION", "PREGUNTA", "IDEA",
                                    "HIPÓTESIS", "HYPOTHESIS", "PENDIENTE", "OPEN"):
                speakers[name] = speakers.get(name, 0) + 1
    people = [name for name, n in sorted(speakers.items(), key=lambda kv: -kv[1])]
    return people, clean


def looks_like_transcript(text: str, path_parts: tuple[str, ...] = ()) -> bool:
    lowered = {p.lower() for p in path_parts}
    if any(any(key in part for key in ("transcrip", "meet", "minut"))
           for part in lowered):
        return True
    people, clean = parse_transcript(text)
    speaker_lines = sum(1 for line in clean.splitlines() if SPEAKER_RE.match(line))
    return len(people) >= 2 and speaker_lines >= MIN_SPEAKER_LINES
