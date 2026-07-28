"""Tests del motor de comunidad (autocomentario).

Sale del benchmark: las tres cuentas del nicho con mejor engagement se comentan
a sí mismas el post recién publicado para arrancar el hilo.
"""
from __future__ import annotations

from app.services.instagram import community

CAPTION = """Hay versos que se te quedan dentro sin pedir permiso.

«Standby» · Extremoduro · Agila (1996)

¿Hay algún verso suyo que te sepas de memoria sin quererlo?

#Música #Extremoduro #Robe

🕯️ Día 230 sin Robe · #DíasSinRobe"""


def test_usa_la_pregunta_del_caption():
    """No inventa texto nuevo: repite la pregunta que ya lleva la pieza."""
    assert (
        community.primer_comentario(CAPTION)
        == "¿Hay algún verso suyo que te sepas de memoria sin quererlo?"
    )


def test_sin_pregunta_no_comenta():
    """En tono sobrio no hay pregunta, y no se fuerza una."""
    sobrio = "Un día como hoy nació Robe.\n\nLe recordamos, en su memoria."
    assert community.primer_comentario(sobrio) is None


def test_caption_vacio():
    assert community.primer_comentario("") is None
    assert community.primer_comentario(None) is None


def test_no_confunde_un_hashtag_con_una_pregunta():
    assert community.primer_comentario("#Extremoduro #Robe") is None


def test_comentar_devuelve_el_texto_publicado(monkeypatch):
    enviados = {}

    def falso(media_id, texto):
        enviados["media_id"] = media_id
        enviados["texto"] = texto
        return "com_1", "Comentado"

    monkeypatch.setattr(community.graph_api, "comment_on_media", falso)
    ok, texto = community.comentar_post("MEDIA_1", CAPTION)
    assert ok
    assert enviados["media_id"] == "MEDIA_1"
    assert texto.startswith("¿Hay algún verso")


def test_si_falla_el_comentario_no_revienta(monkeypatch):
    monkeypatch.setattr(
        community.graph_api, "comment_on_media", lambda *a: (None, "sin permiso")
    )
    ok, msg = community.comentar_post("MEDIA_1", CAPTION)
    assert not ok
    assert "permiso" in msg


def test_la_bandeja_solo_trae_lo_que_falta_por_contestar(monkeypatch):
    monkeypatch.setattr(
        community.graph_api, "list_comments",
        lambda *a, **k: ([
            {"id": "1", "username": "fan1", "text": "grande"},
            {"id": "2", "username": "fan2", "text": "ya contestado",
             "replies": {"data": [{"id": "r1"}]}},
            {"id": "3", "username": "entreinterioresrobe", "text": "el nuestro"},
        ], "OK"),
    )
    pendientes = community.comentarios_sin_responder("MEDIA_1")
    assert [c["id"] for c in pendientes] == ["1"]


def test_no_hay_likes_ni_follows_automaticos():
    """Regla dura: no existe endpoint oficial y arriesgaría la cuenta."""
    import inspect
    fuente = inspect.getsource(community)
    for prohibido in ("def dar_like", "def seguir", "/likes", "/following"):
        assert prohibido not in fuente
