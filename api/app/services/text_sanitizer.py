"""Saneado determinista de texto generado por LLM.

Red de seguridad: aunque el SYSTEM_PROMPT prohíbe el em-dash y otras marcas
de IA, el modelo a veces se cuela. `strip_ai_tells` limpia el texto de
forma mecánica antes de persistirlo.

El em-dash «—» (U+2014) y el en-dash «–» (U+2013) son el delator nº1 de
texto de ChatGPT. Los sustituimos según el contexto:
  - rodeado de espacios  " — "  → ", "   (inciso)
  - pegado entre palabras "x—y"  → "x, y"
  - al principio de línea (lista) "— item" → "- item"
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# Reglas de sustitución de dashes
# --------------------------------------------------------------------------- #
_DASHES = "—–―"  # — – ―

# guion al inicio de línea (item de lista) → guion ASCII
_RE_LIST_DASH = re.compile(rf"^(\s*)[{_DASHES}]\s+", re.MULTILINE)
# " — " inciso entre espacios → ", "
_RE_SPACED_DASH = re.compile(rf"\s+[{_DASHES}]\s+")
# "palabra—palabra" pegado → "palabra, palabra"
_RE_TIGHT_DASH = re.compile(rf"(\w)[{_DASHES}](\w)")
# cualquier dash residual → coma
_RE_ANY_DASH = re.compile(rf"[{_DASHES}]")

_RE_MULTISPACE = re.compile(r"[ \t]{2,}")
_RE_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")


def strip_ai_tells(text: str | None) -> str | None:
    """Limpia marcas de IA de `text`. Devuelve None si la entrada es None.

    No toca enlaces markdown ni el contenido entre comillas (aunque las
    sustituciones son seguras igualmente — un em-dash dentro de una cita
    también es indeseable)."""
    if text is None:
        return None
    if not text:
        return text

    out = text
    # 1) guion de lista al inicio de línea
    out = _RE_LIST_DASH.sub(r"\1- ", out)
    # 2) inciso con espacios → coma
    out = _RE_SPACED_DASH.sub(", ", out)
    # 3) dash pegado entre palabras → coma
    out = _RE_TIGHT_DASH.sub(r"\1, \2", out)
    # 4) cualquier dash suelto restante → coma
    out = _RE_ANY_DASH.sub(", ", out)
    # 5) normalizar espacios
    out = _RE_MULTISPACE.sub(" ", out)
    out = _RE_SPACE_BEFORE_PUNCT.sub(r"\1", out)
    # 6) limpiar comas duplicadas que hayan podido surgir
    out = re.sub(r",\s*,", ",", out)
    return out
