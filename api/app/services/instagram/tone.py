"""Clasificación del tono de un tema, para adaptar el caption.

Distingue contenido luctuoso o conmemorativo ('sober') del resto ('neutral').
Un post sobre la muerte de Robe, un homenaje o un reconocimiento póstumo no
puede cerrar con el gancho festivo de siempre ('flipa con lo que encuentra')
ni llevar emojis de fuego: sería frívolo. El tono manda sobre el CTA, el emoji
del chip y el prompt editorial.

Es deliberadamente conservador: ante la duda, NO marca sobrio (no queremos
apagar el tono de todo). Pero cualquier señal clara de duelo/homenaje sí lo
marca, porque equivocarse hacia el respeto es el lado seguro.
"""
from __future__ import annotations

import re

# Señales de duelo, despedida o conmemoración. Incluye los homenajes/tributos
# y reconocimientos póstumos: son actualidad legítima, pero piden tono sobrio.
_SOBER = re.compile(
    r"("
    r"\bmuere\b|\bmuri[oó]\b|ha\s+muerto|\bfallec\w+|\bfallecimiento\b|"
    r"\bdefunci[oó]n\b|\bmuerte\b|\bp[oó]stum\w+|\bobituario\b|in\s+memoriam|"
    r"\bhomenaje\w*|\btributo\w*|\bausencia\b|\bdescanse\b|\bluto\b|"
    r"\bdespedida\b|\bfuneral\w*|\bsepelio\b|\bentierro\b|nos\s+dej[oó]|"
    r"tras\s+su\s+muerte|\bsin\s+robe\b|ech\w+(?:\s+\w+){0,2}\s+de\s+menos|su\s+recuerdo|"
    r"en\s+su\s+memoria|le\s+recordamos|a\s+t[ií]tulo\s+p[oó]stumo"
    r")",
    re.IGNORECASE,
)


def classify(title: str, summary: str = "") -> str:
    """Devuelve 'sober' para temas luctuosos/conmemorativos, 'neutral' si no."""
    if _SOBER.search(f"{title or ''} {summary or ''}"):
        return "sober"
    return "neutral"
