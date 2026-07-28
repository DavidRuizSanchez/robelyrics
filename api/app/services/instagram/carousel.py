"""Carruseles: decide si un tema los merece y compone sus diapositivas.

El benchmark del nicho fue claro: el post con más engagement de todos los
estudiados (7.273 me gusta) era un carrusel de diseño donde **el verso ES la
pieza gráfica**, mientras que las tarjetas automáticas de plantilla se quedaban
en 100-200. Esto es el motor para dejar de publicar solo tarjetas sueltas.

Dos piezas:
  - `plan(topic, content_type)` → los specs de diapositiva, o None si el tema no
    da para un carrusel con sustancia (entonces se publica foto única, que sigue
    siendo el camino por defecto).
  - `render(topic, specs, slot)` → los JPG en disco.

REGLA HEREDADA de `publisher.prepare`: en evergreen NO se llama al LLM. El texto
de las diapositivas sale del corpus verificado o no hay carrusel. Un carrusel
inventado sería exactamente el fallo que todo el proyecto evita.

LIMITACIÓN CONOCIDA: la portada usa la imagen real del post (foto, portada de
disco o arte IA) y las diapositivas siguientes van sobre fondo degradado de la
misma paleta. Queda coherente, pero no es el "mismo plano recorrido" ideal —
derivar el fondo de la portada (paneo/zoom) está pendiente.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re

from PIL import Image, ImageDraw

from app.services.instagram import config, imaging

logger = logging.getLogger(__name__)

# Menos de 2 no es carrusel; más de 5 cansa y multiplica el coste de revisión.
MIN_SLIDES = 2
MAX_SLIDES = 5


# --------------------------------------------------------------------------- #
# Planificación
# --------------------------------------------------------------------------- #
def _frases(texto: str, minimo: int = 40) -> list[str]:
    """Trocea en frases con sustancia (las muy cortas no llenan una diapositiva)."""
    limpio = re.sub(r"\s+", " ", (texto or "").strip())
    if not limpio:
        return []
    trozos = re.split(r'(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÑ«¿¡"])', limpio)
    return [t.strip() for t in trozos if len(t.strip()) >= minimo]


def plan(topic: dict, content_type: str) -> list[dict] | None:
    """Specs de las diapositivas, o None para seguir con foto única.

    Cada spec es `{"layout": ..., "text": ..., "kicker": ...}`.
    """
    corpus = topic.get("corpus") or {}
    titulo = (topic.get("headline") or topic.get("title") or "").strip()
    cuerpo = (topic.get("caption_body") or topic.get("summary") or "").strip()

    specs: list[dict] = [{"layout": "cover", "text": titulo}]

    if content_type == "quote":
        # El verso ya es la portada; el desarrollo es su ficha y su contexto.
        if not (corpus.get("song") and corpus.get("album")):
            return None
        atribucion = f'«{corpus["song"]}»'
        if corpus.get("artist"):
            atribucion += f'\n{corpus["artist"]}'
        if corpus.get("album"):
            anio = f' ({corpus["year"]})' if corpus.get("year") else ""
            atribucion += f'\n{corpus["album"]}{anio}'
        specs.append({"layout": "fact", "text": atribucion, "kicker": "DE DÓNDE SALE"})

    elif content_type in ("anecdote", "robe_quote"):
        beats = _frases(cuerpo)
        if len(beats) < 1:
            return None
        for i, b in enumerate(beats[: MAX_SLIDES - 2], start=1):
            specs.append({"layout": "verse", "text": b, "kicker": f"{i:02d}"})

    elif content_type == "ephemeris":
        if not cuerpo:
            return None
        specs.append({"layout": "fact", "text": cuerpo, "kicker": "UN DÍA COMO HOY"})

    else:  # news / blog
        beats = _frases(cuerpo)
        if len(beats) < 2:
            return None
        for i, b in enumerate(beats[: MAX_SLIDES - 2], start=1):
            specs.append({"layout": "fact", "text": b, "kicker": f"CLAVE {i:02d}"})

    specs.append({"layout": "closing", "text": ""})

    if len(specs) < MIN_SLIDES + 1:  # portada + 1 desarrollo + cierre
        return None
    return specs[:MAX_SLIDES]


# --------------------------------------------------------------------------- #
# Composición
# --------------------------------------------------------------------------- #
def _puntos_progreso(draw, indice: int, total: int) -> None:
    """Los puntitos del carrusel: firma de continuidad entre diapositivas."""
    r, sep = 6, 22
    ancho = total * sep - (sep - 2 * r)
    x = (imaging.SIZE[0] - ancho) // 2
    y = imaging.SIZE[1] - 56
    for i in range(total):
        color = imaging.COL_GRANATE if i == indice else (90, 84, 78)
        draw.ellipse([x, y, x + 2 * r, y + 2 * r], fill=color)
        x += sep


def _marca(draw, y: int) -> None:
    fuente = imaging._mono(15)
    imaging._draw_tracked(
        draw, (imaging.MARGIN, y), "ENTRE INTERIORES", fuente,
        imaging.COL_MUTED, tracking=4,
    )


def _slide(topic: dict, spec: dict, indice: int, total: int, seed: int) -> Image.Image:
    """Compone una diapositiva que NO es la portada."""
    layout = spec.get("layout", "verse")
    texto = (spec.get("text") or "").strip()

    fondo = imaging._gradient_background(seed + indice * 977)
    img = imaging._treat(fondo, has_photo=False)
    draw = ImageDraw.Draw(img)

    ancho_texto = imaging.SIZE[0] - 2 * imaging.MARGIN

    if spec.get("kicker"):
        imaging._draw_tracked(
            draw, (imaging.MARGIN, imaging.MARGIN), spec["kicker"][:24],
            imaging._mono(15), imaging.COL_GRANATE, tracking=5,
        )

    if layout == "closing":
        titulo = f"Día {config.dias_sin_robe()} sin Robe"
        fuente, lineas, alto = imaging._fit_headline(
            draw, titulo, ancho_texto, 320, 3
        )
        y = (imaging.SIZE[1] - len(lineas) * alto) // 2 - 40
        for ln in lineas:
            w = draw.textlength(ln, font=fuente)
            draw.text(((imaging.SIZE[0] - w) / 2, y), ln, font=fuente,
                      fill=imaging.COL_PAPER)
            y += alto
        cta = "MÁS EN ENTREINTERIORES.COM"
        fuente_cta = imaging._mono(17)
        w = imaging._tracked_width(draw, cta, fuente_cta, 4)
        imaging._draw_tracked(
            draw, ((imaging.SIZE[0] - w) / 2, y + 28), cta, fuente_cta,
            imaging.COL_GRANATE, tracking=4,
        )

    elif layout == "verse":
        # Verso o frase literaria: centrado, en itálica, con aire.
        fuente, lineas, alto = imaging._fit_headline(
            draw, texto, ancho_texto, 620, 8
        )
        y = (imaging.SIZE[1] - len(lineas) * alto) // 2
        for ln in lineas:
            w = draw.textlength(ln, font=fuente)
            draw.text(((imaging.SIZE[0] - w) / 2, y), ln, font=fuente,
                      fill=imaging.COL_PAPER)
            y += alto
        _marca(draw, imaging.SIZE[1] - 104)

    else:  # "fact": bloque alineado a la izquierda con barra granate
        lineas_txt = texto.split("\n")
        fuente, _, alto = imaging._fit_headline(
            draw, lineas_txt[0], ancho_texto - 28, 520, 6
        )
        todas: list[str] = []
        for parrafo in lineas_txt:
            todas.extend(imaging._wrap(draw, parrafo, fuente, ancho_texto - 28))
        y = (imaging.SIZE[1] - len(todas) * alto) // 2
        draw.rectangle(
            [imaging.MARGIN - 18, y, imaging.MARGIN - 12, y + len(todas) * alto],
            fill=imaging.COL_GRANATE,
        )
        for ln in todas:
            draw.text((imaging.MARGIN, y), ln, font=fuente, fill=imaging.COL_PAPER)
            y += alto
        _marca(draw, imaging.SIZE[1] - 104)

    _puntos_progreso(draw, indice, total)
    return img


def _marcar_portada(ruta: str, total: int) -> None:
    """Añade los puntos de progreso y el «DESLIZA →» a la tarjeta de portada.

    La portada la genera el motor de siempre, que no sabe nada de carruseles. Sin
    esta marca nadie sabe que hay más diapositivas detrás y el carrusel se lee
    como una foto suelta — que es justo lo que se quería dejar atrás.
    """
    img = Image.open(ruta).convert("RGB")
    draw = ImageDraw.Draw(img)
    aviso = "DESLIZA →"
    fuente = imaging._mono(16)
    ancho = imaging._tracked_width(draw, aviso, fuente, 4)
    imaging._draw_tracked(
        draw,
        (imaging.SIZE[0] - imaging.MARGIN - ancho, imaging.SIZE[1] - 104),
        aviso, fuente, imaging.COL_GRANATE, tracking=4,
    )
    _puntos_progreso(draw, 0, total)
    img.save(ruta, "JPEG", quality=92)


def render(topic: dict, specs: list[dict], slot: int = 1) -> tuple[list[str], bool]:
    """Genera todas las diapositivas. Devuelve (rutas, usó_foto_real).

    La portada la hace el motor de siempre (`imaging.generate`), así que un
    carrusel arranca exactamente con la tarjeta que ya sabíamos hacer, y luego
    se le marca la continuidad.
    """
    total = len(specs)
    portada, uso_foto = imaging.generate(topic, slot=slot)
    _marcar_portada(portada, total)
    rutas = [portada]

    titulo = (topic.get("headline") or topic.get("title") or "").strip()
    seed = int(hashlib.md5(f"{titulo}{slot}".encode()).hexdigest(), 16) % 1_000_000
    os.makedirs(config.IMAGES_DIR, exist_ok=True)

    for i, spec in enumerate(specs[1:], start=1):
        img = _slide(topic, spec, i, total, seed)
        ruta = os.path.join(config.IMAGES_DIR, f"post_{seed}_{slot}_{i:02d}.jpg")
        img.save(ruta, "JPEG", quality=92)
        rutas.append(ruta)

    logger.info("[IG] carrusel de %d diapositivas generado (slot %s)", total, slot)
    return rutas, uso_foto
