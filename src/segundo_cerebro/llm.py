"""Capa de razonamiento: entrega el context pack a Claude y devuelve la
respuesta. Opcional — el sistema funciona sin LLM devolviendo el context
pack directamente (útil para inspección y debugging).
"""

from __future__ import annotations

import os

from .models import ContextPack

SYSTEM_PROMPT = """Eres el segundo cerebro de tu usuario: una memoria digital
persistente sobre la que razonas. Recibes un context pack construido desde su
memoria episódica, semántica, decisional, de compromisos y su knowledge graph.

Reglas:
- Responde SOLO a partir del context pack; si falta información, dilo
  explícitamente y sugiere qué capturar.
- Cita la fuente (documento o knowledge object) de cada afirmación relevante.
- Distingue hechos confirmados de hipótesis (campo confidence).
- Respeta la temporalidad: una relación con valid_to ya no está vigente.
- Sé conciso, accionable y en el idioma del usuario."""


def llm_available() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or os.environ.get("ANTHROPIC_PROFILE")
        or (os.path.expanduser("~/.config/anthropic"), os.path.isdir(os.path.expanduser("~/.config/anthropic")))[1]
    )


def answer(pack: ContextPack, model: str | None = None) -> str:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model or os.environ.get("SB_MODEL", "claude-opus-5"),
        max_tokens=16000,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{
            "role": "user",
            "content": f"{pack.to_markdown()}\n---\nPregunta: {pack.query}",
        }],
    )
    return "".join(b.text for b in response.content if b.type == "text")
