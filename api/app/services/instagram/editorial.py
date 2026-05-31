"""Reescritura editorial de una noticia para el caption de Instagram.

Convierte el titular + extracto de una noticia en:
  - un comentario editorial con voz propia de Entre Interiores, SIN mencionar
    el medio de origen ni decir "según…";
  - un titular corto y llamativo para la tarjeta de la imagen.

Regla crítica: no se inventa ningún dato (cifras, fechas, lugares, nombres)
que no esté en el material de partida.

Si OpenAI no está disponible, se devuelve el texto original (degradación
elegante: el post se publica igual, con el titular tal cual).
"""
from __future__ import annotations

import json
import logging
import os

from openai import OpenAI, OpenAIError

logger = logging.getLogger(__name__)

_MODEL = "gpt-4o-mini"

_SYSTEM = (
    "Eres el editor de Entre Interiores, una cuenta de Instagram sobre Robe "
    "Iniesta y Extremoduro. Escribes en español de España, cercano y con "
    "criterio, sin sensacionalismo ni emojis. Comentas la actualidad como si "
    "fuera tuya: NUNCA mencionas el medio del que sale la noticia, ni dices "
    "'según', 'informa' ni nombras periódicos o webs. "
    "REGLA CRÍTICA: no inventes ni un solo dato (cifras de asistentes, fechas, "
    "lugares, nombres) que no aparezca en el material que te dan. Si un dato "
    "no está, no lo menciones. No uses la raya larga (—)."
)


def enrich(topic: dict) -> None:
    """Añade topic['caption_body'], ['headline'] e ['image_query'] (in-place)."""
    if topic.get("caption_body") and topic.get("headline"):
        return
    title = (topic.get("title") or "").strip()
    summary = (topic.get("summary") or "").strip()
    body, headline, image_query = _generate(
        title, summary, topic.get("category", ""), topic.get("tone", "neutral")
    )
    topic["caption_body"] = body or _fallback_body(title, summary)
    topic["headline"] = headline or title
    # Término para buscar una foto CC del protagonista (persona/lugar/grupo).
    topic["image_query"] = image_query or ""


def _fallback_body(title: str, summary: str) -> str:
    if summary and summary.lower() not in title.lower():
        return f"{title}\n\n{summary}"
    return title


def _generate(
    title: str, summary: str, category: str, tone: str = "neutral"
) -> tuple[str | None, str | None, str | None]:
    """Llama a OpenAI. Devuelve (comentario, titular, image_query)."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, None, None
    # En temas luctuosos/conmemorativos, el comentario y el titular deben ser
    # sobrios: ni efusividad, ni ganchos, ni titular "llamativo".
    if tone == "sober":
        nota_tono = (
            "TONO: este tema es luctuoso o conmemorativo (muerte, homenaje, "
            "reconocimiento póstumo). Trátalo con respeto y sobriedad, sin "
            "sensacionalismo, sin signos de exclamación y sin frivolidad."
        )
        nota_titular = (
            '  "titular": una frase corta y sobria (máximo 9 palabras), '
            "con mayúscula inicial y sin punto final."
        )
    else:
        nota_tono = ""
        nota_titular = (
            '  "titular": una frase corta y llamativa (máximo 9 palabras) para '
            "una tarjeta visual, con mayúscula inicial y sin punto final."
        )
    user = (
        f"Categoría: {category}\n"
        f"Titular de la noticia: {title}\n"
        f"Extracto disponible: {summary or '(sin extracto)'}\n"
        f"{nota_tono}\n\n"
        "Devuelve SOLO un objeto JSON con tres claves:\n"
        '  "comentario": de 2 a 4 frases comentando la noticia como Entre '
        "Interiores, sin mencionar ningún medio y sin inventar datos.\n"
        f"{nota_titular}\n"
        '  "image_query": término breve (2-4 palabras, preferiblemente nombres '
        "propios) para buscar una FOTO del protagonista de la noticia: una "
        "persona (p.ej. 'Leiva'), un lugar (p.ej. 'Plasencia'), un grupo o "
        "Robe/Extremoduro. Si no hay un sujeto fotografiable claro, cadena vacía."
    )
    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        return (
            (data.get("comentario") or "").strip(),
            (data.get("titular") or "").strip(),
            (data.get("image_query") or "").strip(),
        )
    except (OpenAIError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("[editorial] OpenAI falló (%s); se usa el texto original.", exc)
        return None, None, None
