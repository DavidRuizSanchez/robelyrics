"""Tests del carrusel: planificación y llamadas a la Graph API.

Sin red: las peticiones HTTP se interceptan y se comprueba QUÉ se manda, que es
donde están los errores caros de este endpoint (un caption en un hijo, un padre
montado antes de que los hijos estén listos…).
"""
from __future__ import annotations

import pytest

from app.services.instagram import carousel, graph_api


# --------------------------------------------------------------------------- #
# Planificación
# --------------------------------------------------------------------------- #
def _topic_quote(**kw) -> dict:
    base = {
        "title": "Un verso cualquiera de la canción",
        "content_type": "quote",
        "corpus": {"song": "Standby", "album": "Agila", "year": 1996,
                   "artist": "Extremoduro"},
        "summary": "«Standby» · Extremoduro · Agila (1996)",
    }
    base.update(kw)
    return base


def test_quote_con_corpus_da_carrusel():
    specs = carousel.plan(_topic_quote(), "quote")
    assert specs is not None
    assert specs[0]["layout"] == "cover"
    assert specs[-1]["layout"] == "closing"


def test_quote_sin_corpus_cae_a_foto_unica():
    """Sin datos verificados no se inventa nada: se publica foto suelta."""
    assert carousel.plan(_topic_quote(corpus={}), "quote") is None


def test_anecdota_corta_no_da_carrusel():
    topic = {"title": "Algo", "summary": "Muy corto.", "corpus": {}}
    assert carousel.plan(topic, "anecdote") is None


def test_anecdota_larga_da_varias_diapositivas():
    cuerpo = (
        "Robe se tatuó unas ballenas en el brazo durante la gira. "
        "El dibujo acabó en la contraportada del disco sin que nadie lo planease. "
        "Años después el propio grupo lo contó en una entrevista larga."
    )
    specs = carousel.plan({"title": "Tatuaje", "summary": cuerpo, "corpus": {}}, "anecdote")
    assert specs is not None
    assert len(specs) >= 3
    assert [s["layout"] for s in specs][1:-1] == ["verse"] * (len(specs) - 2)


def test_nunca_pasa_del_maximo():
    cuerpo = " ".join(
        f"Esta es la frase número {i} y tiene longitud más que suficiente." for i in range(20)
    )
    specs = carousel.plan({"title": "X", "summary": cuerpo, "corpus": {}}, "news")
    assert specs is not None
    assert len(specs) <= carousel.MAX_SLIDES


def test_es_determinista():
    assert carousel.plan(_topic_quote(), "quote") == carousel.plan(_topic_quote(), "quote")


# --------------------------------------------------------------------------- #
# Graph API
# --------------------------------------------------------------------------- #
class _RespFalsa:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class _ClienteFalso:
    """Cliente HTTP de mentira que registra lo que se le manda."""

    def __init__(self, registro, respuestas):
        self.registro = registro
        self.respuestas = respuestas

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, data=None, **kw):
        self.registro.append(("POST", url, data or {}))
        return _RespFalsa(self.respuestas.pop(0))

    def get(self, url, params=None, **kw):
        self.registro.append(("GET", url, params or {}))
        return _RespFalsa({"status_code": "FINISHED", "status": ""})


@pytest.fixture()
def graph(monkeypatch):
    registro: list = []
    respuestas: list = []

    def factory(*a, **kw):
        return _ClienteFalso(registro, respuestas)

    monkeypatch.setattr(graph_api.httpx, "Client", factory)
    monkeypatch.setattr(graph_api.time, "sleep", lambda *_: None)
    monkeypatch.setattr(graph_api.config, "INSTAGRAM_ACCOUNT_ID", "IG123")
    monkeypatch.setattr(graph_api.config, "INSTAGRAM_ACCESS_TOKEN", "TOKEN")
    return registro, respuestas


def test_carrusel_manda_los_campos_correctos(graph):
    registro, respuestas = graph
    respuestas.extend([
        {"id": "hijo1"}, {"id": "hijo2"}, {"id": "padre"}, {"id": "MEDIA_OK"},
    ])
    media_id, msg = graph_api.post_carousel(["u1", "u2"], "el caption")
    assert media_id == "MEDIA_OK", msg

    posts = [r for r in registro if r[0] == "POST"]
    hijo1, hijo2, padre, publicar = posts

    # Los hijos: is_carousel_item y NUNCA caption.
    for hijo in (hijo1, hijo2):
        assert hijo[2]["is_carousel_item"] == "true"
        assert "caption" not in hijo[2]
    # El padre: media_type CAROUSEL, children coma-separados y el caption aquí.
    assert padre[2]["media_type"] == "CAROUSEL"
    assert padre[2]["children"] == "hijo1,hijo2"
    assert padre[2]["caption"] == "el caption"
    # Y se publica el ID del PADRE.
    assert publicar[2]["creation_id"] == "padre"


def test_carrusel_rechaza_tamanos_invalidos(graph):
    for urls in ([], ["solo-una"], [f"u{i}" for i in range(11)]):
        media_id, msg = graph_api.post_carousel(urls, "x")
        assert media_id is None
        assert "entre" in msg


def test_si_falla_un_hijo_no_se_crea_el_padre(graph):
    registro, respuestas = graph
    respuestas.extend([{"id": "hijo1"}, {"error": {"message": "boom"}}])
    media_id, msg = graph_api.post_carousel(["u1", "u2"], "cap")
    assert media_id is None
    assert "hijo 2/2" in msg
    # Solo se intentaron los dos hijos: ningún POST de padre ni de publicación.
    assert len([r for r in registro if r[0] == "POST"]) == 2


def test_foto_unica_sigue_funcionando_igual(graph):
    """Regresión: el camino de siempre no puede haber cambiado."""
    registro, respuestas = graph
    respuestas.extend([{"id": "cont"}, {"id": "MEDIA"}])
    media_id, _ = graph_api.post_photo("http://x/y.jpg", "cap")
    assert media_id == "MEDIA"
    creacion = [r for r in registro if r[0] == "POST"][0]
    assert creacion[2]["image_url"] == "http://x/y.jpg"
    assert creacion[2]["caption"] == "cap"
    assert "media_type" not in creacion[2]
