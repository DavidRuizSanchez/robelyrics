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

from app.services.voice import build_system_prompt

logger = logging.getLogger(__name__)

MODEL = "gpt-4o"

# La fecha del fallecimiento de Robe es referencia explícita en el system
# prompt para que el LLM sepa el marco temporal/emocional.
ROBE_BIRTH_DATE = date(1962, 5, 16)
ROBE_DEATH_DATE = date(2025, 12, 10)

# Voz única del sitio (1ª persona admiradora). Ver app/services/voice.py.
SYSTEM_PROMPT = build_system_prompt(family="blog")
# Voz sobria para NOTICIAS/actualidad (3ª persona cálida pero contenida): evita
# el tono megafan punki en contenido luctuoso o póstumo. Ver app/services/voice.py.
NEWS_SYSTEM_PROMPT = build_system_prompt(family="blog", persona="tercera_calida")


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY no está configurado")
    return OpenAI(api_key=api_key)


def _call(
    user_prompt: str, *, max_tokens: int = 2000, system_prompt: str | None = None
) -> dict[str, Any]:
    client = _client()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
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

    # Saneado anti marcas de IA (em-dash, etc.) sobre los campos de texto.
    from app.services.text_sanitizer import strip_ai_tells
    for field in ("title", "excerpt", "body_md", "meta_title", "meta_description"):
        if isinstance(data.get(field), str):
            data[field] = strip_ai_tells(data[field])
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
    context: str | None = None,
) -> dict[str, Any]:
    """Efeméride personal (cumpleaños o aniversario de fallecimiento).

    `kind` ∈ {"birth", "death"}.
    `years_since` es el número de años que se cumplen hoy.
    `context_notes` opcional: nota corta sobre el momento actual (lo que esté
    pasando en el universo, otras efemérides cercanas) para que el texto
    salga distinto cada año.
    `context` (recomendado): datos y lecturas DOCUMENTADAS de la figura
    (consenso fan destilado + fuentes + cuerpo SEO) para anclar la pieza en
    detalles concretos reales y que no salga genérica.
    """
    today = today or date.today()
    kind_label = {"birth": "cumpleaños", "death": "aniversario de su muerte"}[kind]

    grounding = (context or "").strip()
    grounding_block = (
        "DATOS Y LECTURAS DOCUMENTADAS de esta figura (tu materia prima: "
        "parafrasea y elige UN detalle concreto real de aquí; NO lo cites "
        f"textual ni recites letras):\n{grounding[:3000]}"
        if grounding else
        "(Sin contexto documentado: si no conoces un detalle CONCRETO y real, "
        "escribe poco y honesto; no rellenes con generalidades.)"
    )

    user = f"""\
Escribe una pieza editorial para el blog con motivo del {kind_label} de \
{person_name}. Hoy es {today.isoformat()}; se cumplen {years_since} años desde \
{'su nacimiento' if kind == 'birth' else 'su muerte'}.

Quiero una pieza de 350-500 palabras. Empieza con una imagen concreta (no con \
"hoy se cumplen X años"). Dos o tres secciones con H2 evocadores. Cierra sin \
resumen.

{f'Nota de contexto sobre este momento: {context_notes}' if context_notes else ''}

{grounding_block}

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
    context: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Aniversario de lanzamiento de un disco.

    `context` (recomendado): datos y lecturas DOCUMENTADAS del disco (consenso
    fan destilado de sus canciones + fuentes + cuerpo SEO) para que la pieza
    tenga chicha concreta y no salga genérica.
    """
    today = today or date.today()
    tracks_hint = ""
    if track_titles:
        tracks_hint = (
            "Algunos cortes del disco (no los enumeres todos): "
            + ", ".join(track_titles[:6])
            + "."
        )

    grounding = (context or "").strip()
    grounding_block = (
        "DATOS Y LECTURAS DOCUMENTADAS de este disco (tu materia prima: "
        "parafrasea y elige UN detalle concreto real de aquí; NO lo cites "
        f"textual ni recites letras):\n{grounding[:3000]}"
        if grounding else
        "(Sin contexto documentado: si no conoces un detalle CONCRETO y real de "
        "este disco, escribe poco y honesto; no rellenes con generalidades.)"
    )

    user = f"""\
Hoy {today.isoformat()} se cumplen {years_since} años del lanzamiento de \
"{album_title}" ({release_year}) de {artist_name}.

Escribe una pieza editorial de 400-600 palabras. Habla del disco con la \
distancia justa: lo que significó al salir, cómo ha envejecido, qué se sigue \
escuchando hoy. Sin recap de tracks, sin "el contexto era" — entra ya.

{tracks_hint}

{grounding_block}

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
    context: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Análisis editorial breve de una canción, generado rotativamente.

    `context` (recomendado): datos y lecturas DOCUMENTADAS de la canción
    (consenso fan destilado + fuentes + cuerpo SEO) para que la pieza tenga
    chicha concreta y no salga genérica. `seo_excerpt` se mantiene por
    compatibilidad; si no hay `context` se usa él.
    """
    today = today or date.today()
    grounding = (context or seo_excerpt or "").strip()
    grounding_block = (
        "DATOS Y LECTURAS DOCUMENTADAS de esta canción (tu materia prima: "
        "parafrasea y elige UN detalle concreto real de aquí; NO lo cites "
        f"textual ni recites la letra):\n{grounding[:3000]}"
        if grounding else
        "(Sin contexto documentado: si no conoces un detalle CONCRETO y real de "
        "esta canción, escribe poco y honesto; no rellenes con generalidades.)"
    )
    user = f"""\
Pieza editorial sobre la canción "{song_title}" del disco "{album_title}" \
de {artist_name}. 350-450 palabras.

Habla de la canción concreta apoyándote en datos REALES: una imagen que evoca, \
qué dice (sin recitarla entera), su origen o anécdota si consta, por qué vuelve. \
Nada de análisis genérico que valdría para cualquier canción.

{grounding_block}

Una sección H2 evocadora y concreta, máximo dos. Cierra con un verso o una \
imagen real, no con una conclusión.

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
Reescribe esta noticia con tu voz de fan. Abajo tienes el CUERPO COMPLETO de \
la fuente principal y, si las hay, otras fuentes del mismo evento. NO copies \
frases textuales de ninguna (parafrasea siempre con tus palabras): es \
reescritura, no plagio. La pieza acaba con un enlace a la fuente principal.

Titular original: {headline}
Fuentes (cuerpo completo; cruza la información de todas si hay varias):
\"\"\"
{source_excerpt[:8000]}
\"\"\"

Término que matcheó (probablemente el sujeto principal): {matched_term}
Fuente principal: {source_name}
URL fuente: {source_url}

LO MÁS IMPORTANTE: no te dejes fuera los HECHOS CLAVE del evento. Recoge los \
nombres propios relevantes (quién dijo o hizo qué, dedicatorias, canciones \
interpretadas, premios, personas destacadas) y dales el peso que merecen \
según su importancia real, no según el orden de la fuente. Si en la fuente \
aparece una FIGURA MAYOR de la música (Serrat, Sabina, Amaral, Leiva y \
similares), NO la omitas: merece su hueco aunque la fuente la cite de pasada.

NO INVENTES NADA que no esté en las fuentes: ni apellidos, ni la banda a la \
que pertenece alguien, ni lugares, ni fechas. Si la fuente dice solo "Fito", \
escribe "Fito", no le pongas un apellido. Si no sabes el dato con certeza por \
las fuentes, omítelo. Es preferible un nombre escueto a un dato inventado.

Quiero entre 400 y 700 palabras CON FONDO (mejor pocas ideas hondas que un \
resumen plano). Profundiza: por qué importa esto, cómo conecta con la obra y \
la figura de Robe. Entrada directa, sin "tenemos noticias", sin "recientemente \
se ha sabido". Una o dos secciones H2 concretas. Cierra con una línea tipo: \
"Vía [{source_name}]({source_url})." en su propio párrafo, en cursiva.

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
        # Noticias en voz sobria (3ª cálida contenida), no megafan punki: el tono
        # se adapta a la sensibilidad del hecho (luctuoso ≠ festivo).
        return _call(user, max_tokens=2600, system_prompt=NEWS_SYSTEM_PROMPT)
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


def revoice_post(*, title: str, body_md: str, today: date | None = None) -> dict[str, Any]:
    """Reescribe un post EXISTENTE en la voz del sitio (fan, 1ª persona) SIN
    cambiar los hechos. Para posts sin fuente externa (evergreen, efeméride,
    editorial) que solo necesitan el cambio de voz, no más información.
    """
    today = today or date.today()
    user = f"""\
Reescribe el siguiente post en TU voz (fan en primera persona, la del sitio).

NORMA ESTRICTA: mismos HECHOS y misma información. NO añadas datos, nombres,
fechas ni anécdotas que no estén ya en el texto. NO inventes nada. NO quites
información relevante. Solo cambias el registro y la calidad de la prosa para
que suene a quien ama esto, con hondura. Mantén la estructura en H2 concretos
y conserva el enlace final a la fuente si lo hubiera.

TÍTULO ACTUAL: {title}
TEXTO ACTUAL:
\"\"\"
{body_md[:8000]}
\"\"\"

Devuelve el JSON con todos los campos requeridos.
"""
    try:
        return _call(user, max_tokens=2600)
    except (OpenAIError, ValueError) as exc:
        logger.warning("revoice_post fallback: %s", exc)
        return _fallback(title=title[:80], excerpt="", body_md=body_md)


def generate_evergreen_topic(
    *,
    taxonomy_kind: str,
    taxonomy_name: str,
    taxonomy_description: str | None,
    song_titles: list[str],
    context: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Pieza evergreen sobre una taxonomía (tema/lugar/concepto del catálogo).

    Sirve como relleno garantizado cuando el scraper no produce y las
    efemérides no caen esa semana.

    `context` (recomendado): datos y lecturas DOCUMENTADAS de la taxonomía
    (consenso fan destilado de sus canciones + cuerpo SEO) para anclar el
    ensayo en detalles concretos reales y que no salga genérico.
    """
    today = today or date.today()
    titles_sample = ", ".join(f'"{t}"' for t in song_titles[:8])
    descr = taxonomy_description or ""

    grounding = (context or "").strip()
    grounding_block = (
        "DATOS Y LECTURAS DOCUMENTADAS sobre este tema y las canciones donde "
        "aparece (tu materia prima: parafrasea y elige UN detalle concreto real "
        f"de aquí; NO lo cites textual ni recites letras):\n{grounding[:3000]}"
        if grounding else
        "(Sin contexto documentado: si no conoces un detalle CONCRETO y real, "
        "escribe poco y honesto; no rellenes con generalidades.)"
    )

    user = f"""\
Pieza evergreen sobre un {taxonomy_kind} recurrente en el universo \
Robe/Extremoduro: "{taxonomy_name}". 400-550 palabras.

{f'Descripción interna: {descr}' if descr else ''}

Canciones del catálogo donde aparece (referéncialas sin enumerarlas todas): \
{titles_sample}.

{grounding_block}

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


def generate_seo_article(
    *,
    title: str,
    angle: str | None,
    keywords: list[dict[str, Any]] | None = None,
    context: str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Artículo de blog SEO-driven: responde a una intención de búsqueda
    real, optimizado (con naturalidad) para las `keywords` objetivo.

    `keywords` es la lista [{keyword, volume, ...}] que el research adjuntó
    a la propuesta. La de mayor volumen es la principal.

    `context` (recomendado): datos y lecturas DOCUMENTADAS relacionadas
    (consenso fan destilado + fuentes + cuerpo SEO) para anclar el artículo en
    detalles concretos reales y que no salga genérico.
    """
    today = today or date.today()
    kws = keywords or []
    kws_sorted = sorted(kws, key=lambda k: -(k.get("volume") or 0))
    primary = kws_sorted[0]["keyword"] if kws_sorted else title
    kw_block = (
        "\n".join(
            f"- {k['keyword']} ({k.get('volume') or 0} búsquedas/mes)"
            for k in kws_sorted[:12]
        )
        or "(sin keywords objetivo)"
    )

    grounding = (context or "").strip()
    grounding_block = (
        "DATOS Y LECTURAS DOCUMENTADAS relacionadas (tu materia prima: "
        "parafrasea y elige detalles concretos reales de aquí; NO los cites "
        f"textual ni recites letras):\n{grounding[:3000]}"
        if grounding else
        "(Sin contexto documentado: apóyate solo en información pública y "
        "asumida; si no conoces un detalle CONCRETO y real, no lo inventes ni "
        "rellenes con generalidades.)"
    )

    user = f"""\
Escribe un artículo de blog para Entre Interiores que responda a una
búsqueda real de la gente sobre el universo de Robe Iniesta y Extremoduro.

TÍTULO ORIENTATIVO: {title}
ÁNGULO: {angle or "(libre)"}

KEYWORDS OBJETIVO (lo que la gente teclea en Google, con su volumen):
{kw_block}

{grounding_block}

INSTRUCCIONES:
- Responde de verdad a la intención de búsqueda de la keyword principal
  («{primary}»). Si alguien busca eso, este artículo debe resolverlo.
- Usa la keyword principal en el primer párrafo y en algún H2, con
  naturalidad. Las secundarias, repártelas sin forzar. NADA de
  keyword-stuffing.
- 500-900 palabras. 2-4 secciones con H2 concretos.
- Si el tema es sensible (fallecimiento, familia), trátalo con respeto y
  solo con información pública y asumida. Sin morbo.
- Menciona canciones, discos, personas y lugares por su nombre en texto
  plano: el sistema los enlaza solo.

Devuelve el JSON con todos los campos requeridos. El `title` final puede
mejorar el orientativo, pero debe seguir siendo reconocible para quien
busca «{primary}».
"""
    try:
        return _call(user, max_tokens=2200)
    except (OpenAIError, ValueError) as exc:
        logger.warning("generate_seo_article fallback: %s", exc)
        return _fallback(
            title=title,
            excerpt=angle or f"Sobre {primary}.",
            body_md=f"## {title}\n\n{angle or ''}\n",
        )
