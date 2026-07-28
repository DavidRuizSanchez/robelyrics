"""Tests del vídeo propio (versos animados en formato reel).

El render real invoca ffmpeg y tarda, así que aquí se comprueba la composición
—que es donde estuvieron los dos fallos reales— y los parámetros de la Graph
API. El vídeo completo se revisa a ojo con `sample_reel.py`.
"""
from __future__ import annotations

import pytest
from PIL import Image

from app.services.instagram import graph_api, imaging, video


def _base() -> Image.Image:
    return Image.new("RGB", video.SIZE_REEL, (13, 11, 10))


# --------------------------------------------------------------------------- #
# Composición: los dos fallos que salieron al mirar el vídeo generado
# --------------------------------------------------------------------------- #
def test_el_texto_cabe_dentro_del_margen_de_seguridad():
    """FALLO 1: el zoom de ffmpeg amplía la imagen y cortaba el verso.

    Con zoom máximo 1.09 queda visible ~92% del ancho. El texto tiene que caber
    dentro de eso o se pierde el final de los versos largos.
    """
    verso = "Y ando entre su pelo, y hay un agujero por el que salgo y me pierdo"
    img = video._con_verso(_base(), verso, "«Puta» · Yo, minoría absoluta")

    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    ancho_texto = video.SIZE_REEL[0] - 2 * 160
    fuente, lineas, _ = imaging._fit_text(
        draw, verso, ancho_texto, 700, 5, range(76, 39, -4)
    )
    visible = video.SIZE_REEL[0] / 1.09       # lo que sobrevive al zoom
    for ln in lineas:
        assert draw.textlength(ln, font=fuente) <= visible, f"«{ln}» se sale"


def test_el_fondo_del_reel_no_lleva_texto():
    """FALLO 2: usar `imaging.generate` como fondo duplicaba el verso.

    Esa función ya escribe el titular en la tarjeta, y el reel lo vuelve a
    escribir encima: salía el verso dos veces, solapado consigo mismo.
    """
    import inspect
    fuente = inspect.getsource(video.render_verse_reel)
    assert "imaging.generate(" not in fuente, (
        "el fondo del reel no puede salir de imaging.generate: ya lleva el texto"
    )
    assert "_fondo_limpio" in fuente


def test_el_lienzo_vertical_tiene_proporcion_de_reel():
    salida = video._lienzo_vertical(Image.new("RGB", (1080, 1080), (20, 20, 20)))
    assert salida.size == (1080, 1920)


def test_sin_verso_no_se_genera_nada():
    with pytest.raises(ValueError):
        video.render_verse_reel({"title": "  "})


# --------------------------------------------------------------------------- #
# Graph API
# --------------------------------------------------------------------------- #
def test_el_reel_manda_media_type_reels(monkeypatch):
    enviados: dict = {}

    def falso_create(**campos):
        enviados.update(campos)
        return "cont123", "OK"

    monkeypatch.setattr(graph_api, "_create_media", falso_create)
    monkeypatch.setattr(
        graph_api, "publish", lambda c, **kw: ("MEDIA", f"attempts={kw.get('attempts')}")
    )
    media_id, msg = graph_api.post_reel("http://x/v.mp4", "cap", cover_url="http://x/c.jpg")

    assert media_id == "MEDIA"
    assert enviados["media_type"] == "REELS"
    assert enviados["video_url"] == "http://x/v.mp4"
    assert enviados["caption"] == "cap"
    assert enviados["cover_url"] == "http://x/c.jpg"
    # Y con el polling largo: 15×4 s daría timeout casi siempre con vídeo.
    assert f"attempts={graph_api.REELS_POLL_ATTEMPTS}" in msg
    assert graph_api.REELS_POLL_ATTEMPTS * graph_api.REELS_POLL_INTERVAL >= 300


def test_el_polling_de_video_no_cabe_en_una_peticion_web():
    """Recordatorio vivo: Cloudflare corta a los 100 s (ya pasó con un 524).

    Si este test falla es que alguien bajó el polling; antes de tocarlo, revisar
    que los reels se sigan publicando SOLO desde el cron.
    """
    total = graph_api.REELS_POLL_ATTEMPTS * graph_api.REELS_POLL_INTERVAL
    assert total > 100, "con menos margen el vídeo no termina de procesarse"
