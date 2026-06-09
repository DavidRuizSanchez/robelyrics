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
    "no está, no lo menciones. No uses la raya larga (—). "
    "ROBE INIESTA FALLECIÓ: nunca lo presentes hablando en presente ni haciendo "
    "declaraciones nuevas. Si la noticia recoge ideas u opiniones suyas, "
    "enmárcalas SIEMPRE en pasado ('lo que pensaba Robe', 'Robe decía', 'para "
    "Robe era…'), nunca como una declaración actual."
)


def enrich(topic: dict) -> None:
    """Añade topic['caption_body'], ['headline'], ['image_query'] y
    ['hashtags'] (in-place)."""
    if topic.get("caption_body") and topic.get("headline"):
        return
    title = (topic.get("title") or "").strip()
    summary = (topic.get("summary") or "").strip()
    body, headline, image_query, image_search, hashtags = _generate(
        title, summary, topic.get("category", ""), topic.get("tone", "neutral")
    )
    topic["caption_body"] = body or _fallback_body(title, summary)
    topic["headline"] = headline or title
    # Nombre propio del SUJETO (para el hashtag #Sujeto).
    topic["image_query"] = image_query or ""
    # Query DESAMBIGUADA para buscar su foto en Google Images (con contexto,
    # para no traer homónimos). Vacío si el sujeto no es identificable.
    topic["image_search"] = image_search or ""
    # Hashtags específicos del contenido (#MilongasExtremas, etc.).
    topic["hashtags"] = hashtags or []


def _fallback_body(title: str, summary: str) -> str:
    if summary and summary.lower() not in title.lower():
        return f"{title}\n\n{summary}"
    return title


def _generate(
    title: str, summary: str, category: str, tone: str = "neutral"
) -> tuple[str | None, str | None, str | None, str | None, list[str] | None]:
    """Llama a OpenAI. Devuelve (comentario, titular, image_query, image_search,
    hashtags)."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, None, None, None, None
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
        "Devuelve SOLO un objeto JSON con cinco claves:\n"
        '  "comentario": de 2 a 4 frases comentando la noticia como Entre '
        "Interiores, sin mencionar ningún medio y sin inventar datos.\n"
        f"{nota_titular}\n"
        '  "image_query": el NOMBRE PROPIO del SUJETO que PROTAGONIZA la '
        "noticia (quien hace la acción: el grupo, artista, banda o lugar del "
        "que VA la noticia), para el hashtag. Si es un homenaje/tributo/versión, "
        "el sujeto es QUIEN HOMENAJEA, no Robe. Ej.: en 'Milongas Extremas "
        "homenajea a Robe' es 'Milongas Extremas'; en 'Leiva versiona a "
        "Extremoduro' es 'Leiva'. Si no hay sujeto claro pero va del universo "
        "Extremoduro/Robe, usa 'Extremoduro' o 'Robe' (NUNCA 'Robe Iniesta').\n"
        '  "image_search": una frase de búsqueda en Google Imágenes que '
        "identifique SIN AMBIGÜEDAD al sujeto en su contexto, para encontrar una "
        "foto CORRECTA. Añade SIEMPRE contexto (música, banda, grupo, cantante, "
        "Extremoduro, el programa/lugar...). Ej.: 'Milongas Extremas banda "
        "uruguaya', 'Leiva cantante músico', 'Roberto Iniesta Extremoduro', 'David "
        "Broncano La Revuelta'. MUY IMPORTANTE: si el sujeto es un apellido o "
        "nombre común y NO puedes identificarlo con seguridad (p.ej. 'Pérez' a "
        "secas), NO te inventes contexto: deja image_search VACÍO y usaremos una "
        "foto de Robe/Extremoduro. Mejor genérico-correcto que específico-falso.\n"
        '  "hashtags": lista de 1 a 3 hashtags en CamelCase, sin espacios y sin '
        "tildes, ESPECÍFICOS del contenido (nombres propios de grupos, "
        "personas, lugares o canciones citados). Ej.: [\"#MilongasExtremas\"], "
        '["#Leiva", "#PremiosDeLaMusica"]. NADA de genéricos (#Música, #Rock, '
        "#Extremoduro): esos ya se añaden aparte."
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
        raw_tags = data.get("hashtags") or []
        if isinstance(raw_tags, str):
            raw_tags = [raw_tags]
        hashtags = [_clean_hashtag(t) for t in raw_tags]
        hashtags = [t for t in hashtags if t]
        return (
            (data.get("comentario") or "").strip(),
            (data.get("titular") or "").strip(),
            (data.get("image_query") or "").strip(),
            (data.get("image_search") or "").strip(),
            hashtags,
        )
    except (OpenAIError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("[editorial] OpenAI falló (%s); se usa el texto original.", exc)
        return None, None, None, None, None


def _clean_hashtag(tag: str) -> str:
    """Normaliza un hashtag del LLM: garantiza '#', CamelCase y sin espacios."""
    import re

    raw = (tag or "").strip().lstrip("#")
    raw = re.sub(r"[^\w\s]", "", raw, flags=re.UNICODE).strip()
    if not raw:
        return ""
    # Si ya viene pegado (CamelCase) se respeta; si trae espacios, se capitaliza.
    camel = raw if " " not in raw else "".join(w.capitalize() for w in raw.split())
    return f"#{camel}"
