"""El texto que se quema dentro del clip: un gancho y el dato.

Antes era el título del post («Robe, desde el escenario — La Cubierta, Leganés,
09-10-1999»), que no dice nada como rótulo y además **no cabía**: medido, ocupa
1622 px cuando el hueco son 1044, y como `drawtext` centra, ffmpeg se comía unos
veinte caracteres por los dos lados a la vez.

Ahora son dos líneas con propósitos distintos:

    ¡Menuda locura!                        ← el gancho, grande
    «Si te vas...» · Barcelona 2022        ← el dato, pequeño

El gancho lo escribe el modelo, que es lo que pidió David, pero con el listón
puesto: una exclamación corta y que NO afirme nada. Un rótulo no es un titular;
si dijera «el mejor concierto de su vida» estaría afirmando algo que nadie ha
comprobado. Por eso se le prohíben las cifras y los nombres propios, y lo que
escribe pasa por las mismas guardas que el resto del texto del sitio.

En los clips de Robe hablando no hay gancho: solo el concierto. La transcripción
de un directo está garbleada y no se puede citar lo que dice.
"""
from __future__ import annotations

import logging
import re

from app.services.instagram import captions_moldes, video_clips
from app.services.text_sanitizer import enforce_name_policy

logger = logging.getLogger(__name__)

_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def fecha_larga(fecha) -> str:
    """«9 de octubre de 1999». En un rótulo se lee mejor que 09-10-1999."""
    if fecha is None:
        return ""
    return f"{fecha.day} de {_MESES[fecha.month - 1]} de {fecha.year}"

# Lo que cabe de gancho a tamaño cómodo. No es un número redondo: sale de medir
# con la fuente que usa ffmpeg (`video_clips.ancho_texto`).
GANCHO_MAX_CHARS = 22

# Si el modelo no está, falla o su frase no pasa las guardas. Se elige por hash
# del clip (`captions_moldes._pick`), así que el mismo clip da SIEMPRE el mismo
# rótulo: re-preparar no lo cambia por sorpresa.
GANCHOS_DE_RESPALDO = (
    "¡Qué pasada!",
    "¡Menuda locura!",
    "¡Pelos de punta!",
    "¡Cómo sonaba esto!",
    "¡Escuchad esto!",
    "¡Qué momento!",
    "¡Ahí es nada!",
    "¡Tela con esto!",
)
# Por tipo de momento, cuando encaja mejor que el genérico.
GANCHOS_POR_TIPO = {
    "estribillo": ("¡Todos a una!", "¡Menudo coro!", "¡Qué subidón!"),
    "solo": ("¡Qué manos!", "¡Menudo solo!", "¡Ahí, ahí!"),
    "arranque": ("¡Y arranca!", "¡Ya empieza!", "¡Atentos!"),
}

_SYS = (
    "Pones el rótulo de un clip de un concierto de Extremoduro o de Robe, para "
    "Instagram. Escribes UNA exclamación corta de fan, en español de España, "
    "con la emoción de quien estaba ahí.\n"
    "REGLAS:\n"
    f"- Máximo {GANCHO_MAX_CHARS} caracteres, signos incluidos.\n"
    "- Es una EXCLAMACIÓN, no un titular: no afirmas nada, no das datos, no "
    "hay cifras ni fechas ni nombres propios (el nombre de la canción va en "
    "otra línea, debajo).\n"
    "- Nada de cursiladas ni de frases de folleto («un canto a la libertad», "
    "«pura magia»). Habla como un fan, no como una nota de prensa.\n"
    "- Sin emojis, sin comillas y sin la raya larga.\n"
    'Devuelve JSON: {"gancho": "…"}'
)

_RE_CIFRA = re.compile(r"\d")


def _lleva_nombre_propio(texto: str) -> bool:
    """¿Hay un nombre propio aquí? Un dato va en la otra línea, no en el gancho.

    Se mira palabra a palabra y se SALTA la primera, que va capitalizada por
    serlo. Con una expresión regular y lookbehind se tumbaba «¡Qué pasada!»,
    porque el signo de apertura va pegado a la palabra y no hay espacio que
    mirar detrás.
    """
    palabras = [p.strip("¡!¿?.,;:«»\"'()") for p in (texto or "").split()]
    palabras = [p for p in palabras if p]
    return any(p[:1].isupper() for p in palabras[1:])


def _vale(gancho: str) -> tuple[bool, str]:
    """¿Se puede quemar esto en el vídeo? Determinista y sin coste."""
    g = (gancho or "").strip()
    if not g:
        return False, "vacío"
    if len(g) > GANCHO_MAX_CHARS:
        return False, f"{len(g)} caracteres, no cabe"
    if video_clips.sin_emojis(g) != g:
        return False, "lleva emoji (la fuente del vídeo no los dibuja)"
    if _RE_CIFRA.search(g):
        return False, "lleva cifras: un rótulo exclama, no informa"
    if _lleva_nombre_propio(g):
        return False, "lleva un nombre propio: eso va en la línea del dato"
    if video_clips.ancho_texto(g, video_clips.GANCHO_PX_MIN) > video_clips.ANCHO_UTIL:
        return False, "no entra ni al tamaño mínimo"

    from app.services.instagram import tono_guard

    moldes = tono_guard.moldes_en(g)
    if moldes:
        return False, f"frase de molde: {moldes[0]}"
    return True, ""


def _respaldo(tipo: str, clave: str) -> str:
    """El gancho de la lista, elegido por hash: el mismo clip, el mismo texto."""
    opciones = GANCHOS_POR_TIPO.get(tipo, ()) + GANCHOS_DE_RESPALDO
    return captions_moldes._pick(list(opciones), clave, salt="rotulo") or "¡Qué pasada!"


def gancho(tipo: str, cancion: str | None, clave: str) -> str:
    """Una exclamación para el clip. Si el modelo no sirve, la lista de casa."""
    contexto = f"Momento: {tipo}."
    if cancion:
        contexto += f" Suena «{cancion}» (NO la nombres en el gancho)."
    try:
        from app.services.news_research import _json

        data = _json(_SYS, contexto, max_tokens=60, temperature=0.9)
        propuesto = enforce_name_policy((data or {}).get("gancho", "")) or ""
        ok, motivo = _vale(propuesto)
        if ok:
            return propuesto.strip()
        logger.info("[rotulo] gancho descartado (%s): %s", motivo, propuesto[:40])
    except Exception as exc:  # noqa: BLE001
        logger.warning("[rotulo] sin modelo para el gancho: %s", exc)
    return _respaldo(tipo, clave)


def componer(
    *, tipo: str, cancion: str | None, lugar: str | None, cuando: str | None,
    clave: str, verso: str | None = None,
) -> str:
    """Las dos líneas del rótulo, separadas por un salto.

    En los clips de Robe hablando no hay gancho: la transcripción de un directo
    no es citable, así que se dice dónde y cuándo fue, que sí consta.
    """
    sitio = " · ".join(p for p in (lugar, cuando) if p)

    if tipo == "habla":
        return f"{lugar or 'En directo'}\n{cuando}" if cuando else (lugar or "En directo")

    arriba = gancho(tipo, cancion, clave)
    if cancion:
        abajo = f"«{cancion}»" + (f" · {sitio}" if sitio else "")
    elif verso:
        # Sin título de canción, el verso de NUESTRA letra (nunca el de Whisper).
        abajo = f"«{verso}»"
    else:
        abajo = sitio
    return f"{arriba}\n{abajo}".strip()
