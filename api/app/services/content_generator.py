"""Generador de contenido editorial para el blog de Entre Interiores.

A diferencia de `scripts/seo/common.py` (artículos SEO largos en tercera
persona neutral), este módulo produce **piezas cortas de blog** con voz
editorial cercana, sin "marcas de IA", para publicación automática.

Funciones disponibles:
  - generate_anniversary       efeméride Robe (nacimiento/muerte)
  - generate_album_anniversary aniversario de lanzamiento de un disco
  - generate_song_spotlight    análisis editorial de una canción
  - rewrite_news_editorial     reescritura editorial de una noticia externa
  - generate_evergreen_topic   pieza sobre una taxonomía (tema/lugar/concepto)

Cada función devuelve un dict con:
    {
      "title": str (≤80 chars),
      "excerpt": str (≤200 chars, 1-2 frases),
      "body_md": str (markdown sin H1),
      "meta_title": str (≤60),
      "meta_description": str (≤155),
    }

Modelo: gpt-4o (consistente con `scripts/seo/common.py`).
Fallback determinista si el LLM falla — devuelve plantilla simple para que el
post se publique igual con texto "honesto" en vez de bloquear el cron.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date
from typing import Any

from openai import OpenAI, OpenAIError

logger = logging.getLogger(__name__)

MODEL = "gpt-4o"

# La fecha del fallecimiento de Robe es referencia explícita en el system
# prompt para que el LLM sepa el marco temporal/emocional.
ROBE_BIRTH_DATE = date(1962, 5, 16)
ROBE_DEATH_DATE = date(2025, 12, 10)

SYSTEM_PROMPT = """\
Eres redactor del blog "Entre Interiores", un homenaje editorial nocturno a \
Robe Iniesta (1962-2025) y Extremoduro. Escribes en español natural, voz \
cercana y personal. Tu lector ya conoce a Robe — no le explicas lo obvio.

REGLAS FUNDAMENTALES. Si rompes una, el texto se descarta:

VOZ Y TONO
- Habla en primera persona plural ("hemos escuchado", "nos acompañó") o \
  segunda del singular ("vuelves a poner"). Nunca primera del singular.
- Tono nocturno, editorial, con ternura. No épico ni grandilocuente.
- Castellano natural. Modismos puntuales bienvenidos. No regionalismos forzados.

PROHIBIDO ABSOLUTO
- Frases meta sobre la propia escritura: "en este post", "vamos a hablar", \
  "como veremos", "es importante destacar", "cabe mencionar", "en resumen", \
  "vale la pena", "en conclusión", "para terminar", "a continuación".
- Bullets excesivos. Prefiere prosa. Máximo 1 lista corta por pieza si añade claridad.
- Adjetivos vacíos: "increíble", "espectacular", "memorable", "icónico", \
  "legendario", "magistral", "imprescindible".
- Estructura tipo IA: intro-desarrollo-conclusión explícita. Empieza por una \
  imagen concreta, una escena, un verso.
- Cualquier referencia a "modelo de lenguaje", "inteligencia artificial", \
  "como IA", "no puedo confirmar", "según la información disponible".
- Encabezados genéricos: "Introducción", "Conclusión", "Contexto".

ESTRUCTURA
- SIN H1 (lo pone la plantilla del sitio).
- 2-4 secciones máximo. Encabezados H2 cortos y evocadores ("La voz que se \
  quedó", "Plasencia, sábado al sol"), NO genéricos.
- Cierra con una frase ancla, no con un resumen.

CONOCIMIENTO
- Si no estás seguro de un dato concreto (fecha exacta, productor, anécdota), \
  omítelo o redondea ("a finales de los noventa", "en una entrevista de \
  aquellos años"). Nunca inventes.
- Robe falleció el 10 de diciembre de 2025. El tono asume el duelo presente \
  pero asumido — no es necrológica fresca, es homenaje continuado.

SALIDA OBLIGATORIA — JSON estricto, exactamente esta forma:
{
  "title": "<≤80 chars, sin comillas internas>",
  "excerpt": "<1-2 frases, ≤200 chars>",
  "body_md": "<markdown sin H1, con H2/H3>",
  "meta_title": "<≤60 chars>",
  "meta_description": "<≤155 chars>"
}
"""


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY no está configurado")
    return OpenAI(api_key=api_key)


def _call(user_prompt: str, *, max_tokens: int = 2000) -> dict[str, Any]:
    client = _client()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
        max_tokens=max_tokens,
    )
    raw = resp.choices[0].message.content or ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido: {exc}; raw={raw[:200]}") from exc

    required = {"title", "excerpt", "body_md", "meta_title", "meta_description"}
    missing = required - set(data.keys())
    if missing:
        raise ValueError(f"Faltan campos en la salida: {missing}")
    return data


def _fallback(
    *, title: str, excerpt: str, body_md: str, slug_hint: str = ""
) -> dict[str, Any]:
    """Texto determinista para cuando el LLM falla. No es ideal pero permite
    que el cron no se atasque y el admin pueda revisar/editar."""
    return {
        "title": title[:80],
        "excerpt": excerpt[:200],
        "body_md": body_md,
        "meta_title": title[:60],
        "meta_description": excerpt[:155],
    }


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
def generate_anniversary(
    kind: str,
    *,
    person_name: str,
    years_since: int,
    today: date | None = None,
    context_notes: str | None = None,
) -> dict[str, Any]:
    """Efeméride personal (cumpleaños o aniversario de fallecimiento).

    `kind` ∈ {"birth", "death"}.
    `years_since` es el número de años que se cumplen hoy.
    `context_notes` opcional: nota corta sobre el momento actual (lo que esté
    pasando en el universo, otras efemérides cercanas) para que el texto
    salga distinto cada año.
    """
    today = today or date.today()
    kind_label = {"birth": "cumpleaños", "death": "aniversario de su muerte"}[kind]

    user = f"""\
Escribe una pieza editorial para el blog con motivo del {kind_label} de \
{person_name}. Hoy es {today.isoformat()}; se cumplen {years_since} años desde \
{'su nacimiento' if kind == 'birth' else 'su muerte'}.

Quiero una pieza de 350-500 palabras. Empieza con una imagen concreta (no con \
"hoy se cumplen X años"). Dos o tres secciones con H2 evocadores. Cierra sin \
resumen.

{f'Nota de contexto sobre este momento: {context_notes}' if context_notes else ''}

Devuelve el JSON con todos los campos requeridos.
"""
    try:
        return _call(user, max_tokens=1500)
    except (OpenAIError, ValueError) as exc:
        logger.warning("generate_anniversary fallback: %s", exc)
        return _fallback(
            title=f"{years_since} {kind_label.split()[0]} sin {person_name}"
            if kind == "death"
            else f"{years_since} velas para {person_name}",
            excerpt=f"Hoy hace {years_since} años. Volvemos a poner una de sus canciones.",
            body_md=(
                f"## Hoy\n\nHace {years_since} años, {person_name}.\n\n"
                f"Volvemos a sus canciones, a su voz, a las cosas que dijo "
                f"y a las que dejó sin decir.\n"
            ),
        )


def generate_album_anniversary(
    *,
    album_title: str,
    artist_name: str,
    years_since: int,
    release_year: int,
    track_titles: list[str] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Aniversario de lanzamiento de un disco."""
    today = today or date.today()
    tracks_hint = ""
    if track_titles:
        tracks_hint = (
            "Algunos cortes del disco (no los enumeres todos): "
            + ", ".join(track_titles[:6])
            + "."
        )

    user = f"""\
Hoy {today.isoformat()} se cumplen {years_since} años del lanzamiento de \
"{album_title}" ({release_year}) de {artist_name}.

Escribe una pieza editorial de 400-600 palabras. Habla del disco con la \
distancia justa: lo que significó al salir, cómo ha envejecido, qué se sigue \
escuchando hoy. Sin recap de tracks, sin "el contexto era" — entra ya.

{tracks_hint}

Dos o tres secciones con H2 evocadores. Cierra con una imagen, no con \
"sigue siendo imprescindible" ni similares.

Devuelve el JSON con todos los campos requeridos.
"""
    try:
        return _call(user, max_tokens=1800)
    except (OpenAIError, ValueError) as exc:
        logger.warning("generate_album_anniversary fallback: %s", exc)
        return _fallback(
            title=f"{album_title}: {years_since} años después",
            excerpt=f"Vuelve a poner {album_title}. Se cumplen {years_since} años.",
            body_md=(
                f"## {years_since} años\n\nSalió en {release_year}. Hoy lo "
                f"volvemos a poner.\n\nNo todos los discos resisten así.\n"
            ),
        )


def generate_song_spotlight(
    *,
    song_title: str,
    album_title: str,
    artist_name: str,
    seo_excerpt: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Análisis editorial breve de una canción, generado rotativamente."""
    today = today or date.today()
    seo_hint = (
        f"Como contexto interno (no lo cites textual): {seo_excerpt[:500]}"
        if seo_excerpt else ""
    )
    user = f"""\
Pieza editorial sobre la canción "{song_title}" del disco "{album_title}" \
de {artist_name}. 350-450 palabras.

Habla de la canción concreta: una imagen que evoca, qué dice (sin recitarla \
entera), por qué vuelve. No análisis técnico-académico — voz lectora de \
sábado por la tarde.

{seo_hint}

Una sección H2 evocadora, máximo dos. Cierra con un verso o una imagen, no \
con una conclusión.

Devuelve el JSON con todos los campos requeridos.
"""
    try:
        return _call(user, max_tokens=1500)
    except (OpenAIError, ValueError) as exc:
        logger.warning("generate_song_spotlight fallback: %s", exc)
        return _fallback(
            title=f'"{song_title}"',
            excerpt=f'De "{album_title}". Una de esas que vuelve sola.',
            body_md=(
                f"## {song_title}\n\nDel disco *{album_title}* de "
                f"{artist_name}. Vuelve y vuelve.\n"
            ),
        )


def rewrite_news_editorial(
    *,
    headline: str,
    source_excerpt: str,
    source_url: str,
    source_name: str,
    matched_term: str,
    today: date | None = None,
) -> dict[str, Any]:
    """Reescribe una noticia externa con voz editorial propia.

    NO copia el texto original. Toma los hechos y los reescribe en el tono \
    del blog, citando la fuente al final.

    Salida JSON añade dos campos respecto al estándar:
      - slug: kebab-case corto (3-5 palabras) editorialmente útil
      - image_keywords: 2-4 queries específicas para Wikimedia, ordenadas
        de más específica a más genérica; el caller las prueba en orden
        hasta encontrar una imagen relevante.
    """
    today = today or date.today()
    user = f"""\
Reescribe esta noticia con la voz editorial del blog. NO copies frases \
textuales — toma los hechos y cuéntalos a tu manera. La pieza acaba con un \
enlace a la fuente.

Titular original: {headline}
Resumen / cuerpo de la fuente:
\"\"\"
{source_excerpt[:2000]}
\"\"\"

Término que matcheó (probablemente el sujeto principal): {matched_term}
Fuente: {source_name}
URL fuente: {source_url}

Quiero entre 200 y 400 palabras. Entrada directa, sin "tenemos noticias", sin \
"recientemente se ha sabido". Una sola sección H2 si acaso. Cierra con una \
línea tipo: "Vía [{source_name}]({source_url})." en su propio párrafo, \
en cursiva.

Si el contenido fuente no parece relacionado de verdad con Robe / Extremoduro \
/ el universo de la banda (es un falso positivo del scraper), devuelve un \
title vacío "" en el JSON para señalárnoslo.

ADEMÁS de los campos estándar (title, excerpt, body_md, meta_title, \
meta_description), devuelve también:
  - "slug": kebab-case de 3-5 palabras editorialmente sólido (ej. \
    "retrato-broncano-revuelta", "murales-plasencia-aniversario"). No copies \
    el titular literal; piensa en lo que el lector escribiría como URL.
  - "image_keywords": lista de 2-4 strings que sirvan como query a Wikimedia \
    Commons buscando una imagen RELACIONADA con la noticia. Orden de más \
    específico a más genérico. Ejemplos: ["David Broncano La Revuelta", \
    "Plasencia Cáceres", "Robe Iniesta concierto"]. Evita términos demasiado \
    abstractos. Si no se te ocurre nada relacionado, devuelve [] (sin foto \
    es mejor que una random).

Devuelve el JSON con TODOS los campos.
"""
    try:
        return _call(user, max_tokens=1500)
    except (OpenAIError, ValueError) as exc:
        logger.warning("rewrite_news_editorial fallback: %s", exc)
        return _fallback(
            title=headline[:80],
            excerpt=source_excerpt[:200],
            body_md=(
                f"## Nota\n\n{source_excerpt[:1000]}\n\n"
                f"*Vía [{source_name}]({source_url}).*\n"
            ),
        )


def generate_evergreen_topic(
    *,
    taxonomy_kind: str,
    taxonomy_name: str,
    taxonomy_description: str | None,
    song_titles: list[str],
    today: date | None = None,
) -> dict[str, Any]:
    """Pieza evergreen sobre una taxonomía (tema/lugar/concepto del catálogo).

    Sirve como relleno garantizado cuando el scraper no produce y las
    efemérides no caen esa semana.
    """
    today = today or date.today()
    titles_sample = ", ".join(f'"{t}"' for t in song_titles[:8])
    descr = taxonomy_description or ""
    user = f"""\
Pieza evergreen sobre un {taxonomy_kind} recurrente en el universo \
Robe/Extremoduro: "{taxonomy_name}". 400-550 palabras.

{f'Descripción interna: {descr}' if descr else ''}

Canciones del catálogo donde aparece (referéncialas sin enumerarlas todas): \
{titles_sample}.

No quiero un listado. Quiero un ensayo corto: qué imagen evoca este \
{taxonomy_kind}, por qué aparece tantas veces, cómo lo trata Robe. Dos H2 \
evocadores, no genéricos.

Cierra con una imagen, no con un resumen.

Devuelve el JSON con todos los campos requeridos.
"""
    try:
        return _call(user, max_tokens=1800)
    except (OpenAIError, ValueError) as exc:
        logger.warning("generate_evergreen_topic fallback: %s", exc)
        return _fallback(
            title=f"{taxonomy_name}",
            excerpt=f"Sobre un {taxonomy_kind} que vuelve en sus canciones.",
            body_md=(
                f"## {taxonomy_name}\n\nVuelve canción tras canción.\n"
            ),
        )
