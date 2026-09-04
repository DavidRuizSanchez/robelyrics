"""Moldes sintácticos para el caption: plantilla de ESTRUCTURA, no de TEXTO.

El problema que resuelve este módulo está medido: en los 40 últimos posts
publicados, el 100% abría con la misma línea (`🕯️ Día N sin Robe`) y el 100%
seguía con la misma etiqueta (`🎸 MÚSICA`). En Instagram solo se ve la PRIMERA
LÍNEA antes del «… más», así que quien nos seguía nunca veía de qué iba el post.

Las cuentas del nicho que mejor funcionan hacen lo contrario: repiten un molde
sintáctico y jamás las mismas palabras ("Hay versos que se desnudan sin
tocarte", "Hay canciones que no vienen a entretener. Vienen a levantar del suelo
sin que te des cuenta"). Eso es lo que se imita aquí.

REGLAS DURAS
  - Un molde solo se usa si TODOS sus campos tienen dato real. Si falta uno, ese
    molde queda descartado; nunca se rellena con un valor plausible.
  - Ningún molde afirma AUTORÍA. Robe es el letrista de casi todo, pero no de
    todo («Ama, ama y ensancha el alma» es un poema de Manolo Chinato), y un
    molde que dijera "esto lo escribió Robe" mentiría en esos casos.
  - Ningún molde afirma nada factual que no venga en el contexto: lo que aportan
    es retórica, no datos.
  - La elección es DETERMINISTA (hash del content_key): el mismo post da siempre
    el mismo caption, y re-preparar no lo cambia por capricho.
"""
from __future__ import annotations

import hashlib
import re

# --------------------------------------------------------------------------- #
# Ganchos: la primera línea, lo único que se ve en el feed sin desplegar.
# --------------------------------------------------------------------------- #
# Cada entrada es una plantilla con campos {entre_llaves} que deben existir en el
# contexto. Las que no llevan campos valen siempre (son el suelo garantizado).
HOOKS: dict[str, list[str]] = {
    "quote": [
        "Hay versos que no se leen: se reconocen.",
        "Esto está en «{song}». Y no hacía falta decir más.",
        "Cuatro líneas de «{song}» que aguantan de pie solas.",
        "«{album}», {year}. Y este verso sigue ahí.",
        "Hay frases que se te quedan dentro sin pedir permiso.",
        "De «{song}», y con esto basta.",
        "{year}. Esto ya estaba escrito.",
        "Un verso de «{song}» que no necesita nota al pie.",
        "Lo dijo mejor «{song}» que cualquier explicación.",
        "Hay versos que te encuentran a ti, no al revés.",
    ],
    "robe_quote": [
        "Lo dijo él, y se entiende a la primera.",
        "Hay respuestas que valen más que la pregunta.",
        "Esto lo dejó dicho, y sigue en pie.",
        "No hay que interpretarlo: está dicho tal cual.",
        "Una frase suya para leer dos veces.",
    ],
    "anecdote": [
        "Esto pasó de verdad.",
        "Hay historias que explican una canción entera.",
        "Lo que no se ve detrás de un disco.",
        "Una de esas cosas que no salen en la ficha del disco.",
        "Detrás de «{album}» hay más de lo que parece.",
        "Hay anécdotas que valen por una biografía.",
    ],
    # Las efemérides se parten en dos: un aniversario de disco y un cumpleaños de
    # persona no admiten el mismo texto. Sin esta separación salían cosas como
    # "¿dónde lo escuchasteis por primera vez?" bajo el cumpleaños de Uoho.
    "ephemeris_album": [
        "Un día como hoy.",
        "Hoy hace {years} años de «{album}».",
        "«{album}» cumple {years} años.",
        "Hoy se cumplen {years} años de «{album}».",
        "{year}. El día que salió «{album}».",
    ],
    "ephemeris_person": [
        "Hoy es el cumpleaños de {person}.",
        "Un día como hoy nació {person}.",
        "Hoy toca acordarse de {person}.",
        "{person}, que hoy cumple años.",
    ],
    "ephemeris": [
        "Un día como hoy.",
    ],
    "news": [
        "{headline}",
    ],
    "blog": [
        "{headline}",
    ],
    # Posts que enseñan la web. El gancho promete lo que se ve en la captura.
    "product": [
        "{headline}",
        # `headline_frase`, no `headline_min` + «.»: el titular de estos posts es
        # la consulta real, y muchas son preguntas → «…en Plasencia?.».
        "Esto existe y funciona: {headline_frase}",
        "Lo hemos montado para esto: {headline_frase}",
    ],
}

# --------------------------------------------------------------------------- #
# Preguntas de cierre: abren conversación. Las cuentas con mejor engagement del
# nicho cierran así, y los comentarios que generan son respuestas argumentadas,
# no emojis sueltos.
# --------------------------------------------------------------------------- #
QUESTIONS: dict[str, list[str]] = {
    "quote": [
        "¿Y a ti, qué verso de «{song}» se te quedó dentro?",
        "¿Cuál te pega más fuerte de «{album}»?",
        "¿Qué te recuerda este verso?",
        "¿Dónde estabas la primera vez que escuchaste esto?",
        "¿Hay algún verso suyo que te sepas de memoria sin quererlo?",
    ],
    "robe_quote": [
        "¿Estáis de acuerdo?",
        "¿Qué os parece a vosotros?",
        "¿Os suena de algo lo que dice aquí?",
    ],
    "anecdote": [
        "¿Sabíais esto?",
        "¿Conocíais la historia?",
        "¿Qué otra historia del grupo os sorprendió al descubrirla?",
    ],
    "ephemeris_album": [
        "¿Qué recuerdo tenéis de «{album}»?",
        "¿Cuál es vuestra canción de «{album}»?",
        "¿Dónde lo escuchasteis vosotros por primera vez?",
        "¿Os acordáis de cuándo lo oísteis entero por primera vez?",
    ],
    "ephemeris_person": [
        "¿Con qué canción suya os quedáis?",
        "¿Qué le diríais hoy?",
        "¿Cuál es vuestro momento favorito suyo?",
    ],
    "ephemeris": [
        "¿Qué recordáis vosotros de aquello?",
    ],
    "news": [
        "¿Qué os parece?",
        "¿Cómo lo veis vosotros?",
    ],
    "blog": [
        "¿Qué opináis?",
        "¿Añadiríais algo?",
    ],
    "product": [
        "¿Qué le preguntaríais vosotros?",
        "¿Qué echáis en falta?",
        "¿Lo probáis y me contáis?",
    ],
}

_FIELD_RE = re.compile(r"\{(\w+)\}")


def _pick(options: list[str], key: str, salt: str = "") -> str | None:
    """Elige de forma determinista por hash del `key`. Mismo post → mismo molde.

    Se usa el hash y no `random` a propósito: re-preparar un item (algo que el
    admin hace desde el panel) no debe cambiarle el texto por sorpresa.
    """
    if not options:
        return None
    digest = hashlib.md5(f"{salt}:{key}".encode()).hexdigest()
    return options[int(digest, 16) % len(options)]


def _renderables(templates: list[str], ctx: dict) -> list[str]:
    """Los moldes cuyos campos están TODOS presentes y no vacíos en el contexto."""
    out = []
    for tpl in templates:
        campos = _FIELD_RE.findall(tpl)
        if all(str(ctx.get(c, "")).strip() for c in campos):
            out.append(tpl)
    return out


def _render(tpl: str, ctx: dict) -> str:
    return _FIELD_RE.sub(lambda m: str(ctx.get(m.group(1), "")).strip(), tpl).strip()


def _subtipo(content_type: str, ctx: dict) -> str:
    """Afina el tipo con lo que hay en el contexto.

    Una efeméride de disco y un cumpleaños de persona son cosas distintas y no
    aceptan el mismo texto, pero comparten `content_type` en la cola.
    """
    if content_type == "ephemeris":
        if ctx.get("person"):
            return "ephemeris_person"
        if ctx.get("album"):
            return "ephemeris_album"
    return content_type


def _con_fallback(tabla: dict[str, list[str]], content_type: str, ctx: dict) -> list[str]:
    """Moldes del subtipo y, si no hay ninguno rellenable, los del tipo base."""
    sub = _subtipo(content_type, ctx)
    opciones = _renderables(tabla.get(sub, []), ctx)
    if not opciones and sub != content_type:
        opciones = _renderables(tabla.get(content_type, []), ctx)
    return opciones


def hook(content_type: str, ctx: dict, key: str) -> str | None:
    """Primera línea del caption: lo único visible en el feed sin desplegar.

    Devuelve None si no hay ningún molde rellenable para ese tipo — el llamante
    decide entonces qué poner (normalmente, el titular tal cual).
    """
    tpl = _pick(_con_fallback(HOOKS, content_type, ctx), key, salt="hook")
    return _render(tpl, ctx) if tpl else None


def question(content_type: str, ctx: dict, key: str) -> str | None:
    """Pregunta abierta de cierre, o None si no hay ninguna rellenable."""
    tpl = _pick(_con_fallback(QUESTIONS, content_type, ctx), key, salt="question")
    return _render(tpl, ctx) if tpl else None


def one_sentence_per_line(text: str, max_frases: int = 8) -> str:
    """Trocea un párrafo en una frase por línea.

    Es la forma en que escriben las cuentas del nicho cuyos captions largos
    funcionan: el texto respira y se lee como un poema, no como un teletipo.
    No reescribe nada — solo cambia dónde caen los saltos de línea.
    """
    txt = re.sub(r"\s+", " ", (text or "").strip())
    if not txt:
        return ""
    # Corta tras . ! ? … seguidos de espacio y mayúscula (o comilla de apertura).
    frases = re.split(r'(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÑ«¿¡"])', txt)
    frases = [f.strip() for f in frases if f.strip()]
    if len(frases) > max_frases:
        # No se pierde texto: el excedente se pega a la última línea.
        frases = frases[: max_frases - 1] + [" ".join(frases[max_frases - 1:])]
    return "\n\n".join(frases)
