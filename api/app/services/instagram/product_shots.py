"""Piezas que enseñan la web, compuestas con datos REALES del sitio.

En vez de capturar la pantalla con un navegador —que obligaría a meter Playwright
y sus navegadores en la imagen de producción— se recompone la pantalla con la
misma estética del sitio (fondo casi negro, serif para el contenido, mono granate
para las etiquetas) y **preguntas y respuestas de verdad**, pedidas a la propia
API en el momento de generar.

Eso es lo importante y lo que no se negocia: aquí no hay texto de ejemplo. La
respuesta del consultorio sale de `consult.ask()` y los versos del buscador
semántico salen del buscador. Si la consulta falla, no se genera la pieza — un
post que enseña una funcionalidad con datos inventados sería justo lo contrario
de lo que vende el proyecto.
"""
from __future__ import annotations

import logging
import os

from PIL import Image, ImageDraw

from app.services.instagram import config, imaging

logger = logging.getLogger(__name__)

SIZE = (1080, 1350)          # 4:5, el formato vertical que más ocupa en el feed
MARGEN = 78

# Paleta del sitio (web/tailwind.config.ts).
FONDO = (13, 11, 10)
TINTA = (237, 228, 211)
TINTA_TENUE = (196, 184, 160)
TINTA_APAGADA = (141, 130, 112)
ACENTO = (232, 80, 80)


def _mono(size: int):
    return imaging._mono(size)


def _serif(size: int, weight: int = 400):
    return imaging._cormorant(size, weight=weight)


def _lienzo() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", SIZE, FONDO)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, SIZE[0], 6], fill=ACENTO)
    return img, draw


def _parrafo(
    draw, texto: str, x: int, y: int, fuente, color, ancho: int,
    interlineado: float = 1.42, max_lineas: int | None = None,
) -> int:
    """Escribe un párrafo ajustado al ancho. Devuelve la y final."""
    lineas = imaging._wrap(draw, texto, fuente, ancho)
    if max_lineas and len(lineas) > max_lineas:
        lineas = lineas[:max_lineas]
        lineas[-1] = lineas[-1].rstrip(" .,;:") + "…"
    alto = int(fuente.size * interlineado)
    for ln in lineas:
        draw.text((x, y), ln, font=fuente, fill=color)
        y += alto
    return y


def _pie_marca(draw) -> None:
    fuente = _mono(17)
    imaging._draw_tracked(
        draw, (MARGEN, SIZE[1] - 92), "ENTRE INTERIORES", fuente, ACENTO, tracking=4
    )
    draw.text(
        (MARGEN, SIZE[1] - 62), "entreinteriores.com", font=_mono(15),
        fill=TINTA_APAGADA,
    )


def _centrar(pintar) -> Image.Image:
    """Pinta dos veces: la primera para medir, la segunda ya centrada.

    Sin esto sobraba medio lienzo en blanco debajo del contenido — las
    respuestas y los resultados no siempre ocupan lo mismo, así que la posición
    no se puede fijar a ojo.

    OJO con lo que devuelve `pintar`: es la Y FINAL, no la altura. Midiendo
    desde `MARGEN + 20` y tratando ese número como si fuera el alto, el hueco
    salía inflado en el margen inicial y el contenido quedaba pegado arriba con
    un palmo de negro debajo. Se mide desde 0, y así la Y final ES la altura.
    """
    medidor = ImageDraw.Draw(Image.new("RGB", SIZE, FONDO))
    alto = pintar(medidor, 0)

    img, draw = _lienzo()
    util = SIZE[1] - 150                  # 150 = zona del pie
    offset = max(MARGEN + 20, (util - alto) // 2)
    pintar(draw, offset)
    _pie_marca(draw)
    return img


def consultorio(pregunta: str, respuesta: str, destino: str) -> str:
    """Recompone «Pregúntale al viento» con una pregunta y respuesta reales."""
    img = _centrar(lambda draw, y0: _pintar_consultorio(draw, y0, pregunta, respuesta))
    img.save(destino, "JPEG", quality=93)
    logger.info("[product] consultorio → %s", destino)
    return destino


def _pintar_consultorio(draw, y: int, pregunta: str, respuesta: str) -> int:
    ancho = SIZE[0] - 2 * MARGEN

    imaging._draw_tracked(
        draw, (MARGEN, y), "EL VIENTO RESPONDE", _mono(15), ACENTO, tracking=4
    )
    y += 46
    f_titulo = _serif(78, weight=500)
    draw.text((MARGEN, y), "Pregúntale al viento", font=f_titulo, fill=TINTA)
    y += 108

    imaging._draw_tracked(
        draw, (MARGEN, y), "LE PREGUNTASTE", _mono(14), TINTA_APAGADA, tracking=3
    )
    y += 34
    y = _parrafo(draw, pregunta, MARGEN, y, _serif(40, 500), ACENTO, ancho)
    y += 34

    draw.line([(MARGEN, y), (SIZE[0] - MARGEN, y)], fill=(60, 52, 48), width=1)
    y += 34

    y = _parrafo(
        draw, respuesta, MARGEN, y, _serif(35), TINTA_TENUE, ancho,
        interlineado=1.5, max_lineas=14,
    )
    return y


def buscador(consulta: str, resultados: list[dict], destino: str) -> str:
    """Recompone «Como lo diría Robe» con versos reales del buscador."""
    img = _centrar(lambda draw, y0: _pintar_buscador(draw, y0, consulta, resultados))
    img.save(destino, "JPEG", quality=93)
    logger.info("[product] buscador → %s", destino)
    return destino


def _pintar_buscador(draw, y: int, consulta: str, resultados: list[dict]) -> int:
    ancho = SIZE[0] - 2 * MARGEN

    imaging._draw_tracked(draw, (MARGEN, y), "01", _mono(15), ACENTO, tracking=4)
    y += 42
    draw.text((MARGEN, y), "Como lo diría Robe", font=_serif(74, 500), fill=TINTA)
    y += 100

    # La consulta, como en el campo de búsqueda del sitio.
    draw.text((MARGEN, y), f"«{consulta}»", font=_serif(38), fill=TINTA_TENUE)
    y += 56
    draw.line([(MARGEN, y), (SIZE[0] - MARGEN, y)], fill=(60, 52, 48), width=1)
    y += 40

    for i, r in enumerate(resultados[:2], start=1):
        imaging._draw_tracked(
            draw, (MARGEN, y + 8), f"{i:02d}", _mono(14), ACENTO, tracking=3
        )
        x = MARGEN + 58
        ancho_res = ancho - 58
        y = _parrafo(
            draw, r["verso"], x, y, _serif(44, 500), TINTA, ancho_res,
            interlineado=1.3, max_lineas=3,
        )
        y += 12
        ficha = " · ".join(
            p for p in (r.get("song"), r.get("album"), str(r.get("year") or "")) if p
        )
        imaging._draw_tracked(
            draw, (x, y), ficha.upper()[:52], _mono(14), TINTA_APAGADA, tracking=2
        )
        y += 34
        if r.get("why"):
            imaging._draw_tracked(
                draw, (x, y), "ENCAJA", _mono(13), ACENTO, tracking=3
            )
            y = _parrafo(
                draw, r["why"], x + 76, y - 2, _serif(27), TINTA_TENUE,
                ancho_res - 76, max_lineas=3,
            )
        y += 44
    return y


# --------------------------------------------------------------------------- #
# Datos reales: se piden a la propia web, no se inventan
# --------------------------------------------------------------------------- #
def datos_consultorio(db, pregunta: str) -> dict:
    """Pregunta de verdad al consultorio. Propaga el error si falla."""
    from app.services.consult import ask

    r = ask(db, pregunta)
    if not (r.answer or "").strip():
        raise RuntimeError("el consultorio no devolvió respuesta")
    return {"pregunta": r.question, "respuesta": r.answer}


def datos_buscador(db, consulta: str, k: int = 2) -> list[dict]:
    """Busca de verdad en el buscador semántico. Propaga el error si falla."""
    from sqlalchemy import select

    from app.db.models import User
    from app.routers.search import SemanticIn, semantic

    # El endpoint registra la consulta con el id del usuario, así que se le pasa
    # el admin: la búsqueda queda en la analítica como lo que es, una consulta
    # del sistema para montar la pieza, y no con un usuario falso.
    admin = db.execute(
        select(User).where(User.is_admin.is_(True)).order_by(User.id)
    ).scalars().first()
    if admin is None:
        raise RuntimeError("no hay usuario admin con el que consultar")

    salida = semantic(SemanticIn(query=consulta, k=k), db=db, _user=admin)
    resultados = []
    for hit in salida.results[:k]:
        d = hit.model_dump() if hasattr(hit, "model_dump") else dict(hit)
        cancion = d.get("song") or {}
        album = d.get("album") or {}
        resultados.append({
            "verso": d.get("line_text") or "",
            "song": cancion.get("title"),
            "album": album.get("title"),
            "year": album.get("year"),
            "why": d.get("why"),
        })
    if not resultados or not resultados[0]["verso"]:
        raise RuntimeError("el buscador no devolvió versos")
    return resultados


def _nombre_fichero(slug: str, consulta: str) -> str:
    """Un fichero por (funcionalidad, consulta): dos posts de la misma sección
    con preguntas distintas no pueden pisarse la imagen."""
    import hashlib
    import unicodedata

    base = "".join(
        c for c in unicodedata.normalize("NFD", slug.lower())
        if unicodedata.category(c) != "Mn" and (c.isalnum() or c == "-")
    )
    firma = hashlib.md5(consulta.strip().lower().encode("utf-8")).hexdigest()[:8]
    return f"{base or 'pieza'}-{firma}.jpg"


def componer(db, slug: str, consulta: str, destino_dir: str | None = None) -> str | None:
    """Compone LA pieza de una funcionalidad con UNA consulta concreta.

    Devuelve la ruta, o None si la consulta falla — y entonces no se publica
    nada: un post que promete enseñar algo con datos inventados sería justo lo
    contrario de lo que vende el proyecto.

    Antes esto era `generar()`, que recomponía TODAS las piezas con dos consultas
    fijas y en cada `prepare`: una llamada al LLM y una búsqueda semántica
    completas aunque solo hiciera falta una.
    """
    destino_dir = destino_dir or os.path.join(config.IMAGES_DIR, "product")
    os.makedirs(destino_dir, exist_ok=True)
    destino = os.path.join(destino_dir, _nombre_fichero(slug, consulta))

    try:
        if slug == "pregúntale-al-viento":
            d = datos_consultorio(db, consulta)
            return consultorio(d["pregunta"], d["respuesta"], destino)
        if slug in ("como-lo-diria-robe", "listas-por-mood"):
            return buscador(consulta, datos_buscador(db, consulta), destino)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[product] «%s» sobre %s falló: %s", consulta, slug, exc)
        return None

    logger.info("[product] «%s» no se recompone (vive de su captura)", slug)
    return None


def generar(db, destino_dir: str | None = None) -> dict[str, str]:
    """Compone una pieza de cada funcionalidad recomponible. Devuelve {slug: ruta}.

    Es solo el arranque (poblar el directorio la primera vez). Los posts usan
    `componer()`, que hace UNA con la consulta que toca.
    """
    from app.services.instagram import product_topics

    hechas: dict[str, str] = {}
    for slug in product_topics.FUENTES:
        consultas = product_topics.consultas_para(db, slug)
        if not consultas:
            logger.warning("[product] sin consultas reales para %s", slug)
            continue
        ruta = componer(db, slug, consultas[0], destino_dir)
        if ruta:
            hechas[slug] = ruta
    return hechas


def ficha(slug: str) -> dict:
    """Datos editoriales de una funcionalidad (data/instagram_product.yaml)."""
    import yaml

    from app.services.instagram.evergreen import _data_path

    ruta = _data_path("instagram_product.yaml")
    if not ruta:
        return {}
    data = yaml.safe_load(open(ruta, encoding="utf-8")) or {}
    for f in data.get("funcionalidades") or []:
        if (f.get("slug") or "").strip() == slug:
            return f
    return {}
