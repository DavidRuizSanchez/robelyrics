"""Tests del guard de completitud dentro del camino de publicación.

Un texto puede estar impecable de forma y engañar por lo que calla. El artículo
que lo motiva recorría la discografía entera de Extremoduro, contaba la
disolución y «Mayéutica» (2021), y se paraba ahí: el gate de rigor le dio el
visto bueno porque mide densidad, no cobertura.

Lo que vigilan estos tests es el equilibrio. Que frene lo que engaña, y que NO
frene lo demás: un guard que retiene de más deja el blog sin publicar, y eso ya
pasó once días seguidos en este proyecto.
"""
from __future__ import annotations

import pytest

from app.services import publishing


class _Post:
    def __init__(self, body, kind="evergreen", title="Extremoduro"):
        self.id, self.body_md, self.kind, self.title = 1, body, kind, title
        self.target_keyword = None
        self.status = "draft"
        self.hero_image_url = None
        self.entities = []
        self.slug = "una-entrada"
        self.event_date = None


TRAYECTORIA_SIN_MUERTE = """## La trayectoria de Extremoduro
Deltoya (1992), Pedrá (1995), Agila (1996) y La ley innata (2008) marcaron su
sonido. El 18 de diciembre de 2019 anunciaron su disolución. Robe siguió con
Mayéutica (2021)."""

TRAYECTORIA_COMPLETA = TRAYECTORIA_SIN_MUERTE + """
Robe falleció el 10 de diciembre de 2025, a los 63 años."""


@pytest.fixture()
def rutas(monkeypatch):
    """Anota a dónde se manda el post y corta todo lo que no se está probando."""
    visto = {}

    def _a_revision(db, post, **kw):
        visto["accion"] = "revision"
        return {"action": "pending_review", "post_id": post.id, "scheduled_for": None}

    monkeypatch.setattr(publishing, "propose_for_review", _a_revision)
    return visto


class _Album:
    def __init__(self, title, year):
        self.title, self.year, self.kind = title, year, "studio"


class _DB:
    """Catálogo mínimo. En producción SIEMPRE hay BD detrás: sin ella el
    detector no puede contar discos y se queda callado, que es el lado seguro."""

    _CATALOGO = [("Deltoya", 1992), ("Pedrá", 1995), ("Agila", 1996),
                 ("La ley innata", 2008), ("Mayéutica", 2021),
                 ("Se nos lleva el aire", 2023)]

    def execute(self, _s):
        filas = [(_Album(t, y), "extremoduro") for t, y in self._CATALOGO]

        class _R:
            def all(self_inner):
                return filas

        return _R()


def _corre_guard(post, db=None):
    """Ejecuta solo el tramo del guard, con el mismo código que usa publishing."""
    from app.services.sensitive_topics import revisar
    return revisar(db or _DB(), kind=post.kind, subject=post.title,
                   body_md=post.body_md)


def test_el_texto_que_calla_la_muerte_va_a_revision(rutas):
    rep = _corre_guard(_Post(TRAYECTORIA_SIN_MUERTE))
    assert rep.necesita_revision


def test_el_mismo_texto_contandolo_no_se_frena(rutas):
    """La otra mitad del equilibrio: si también frenara esto, no se publicaría nada."""
    rep = _corre_guard(_Post(TRAYECTORIA_COMPLETA))
    assert not rep.necesita_revision


def test_una_pieza_que_no_va_de_robe_no_se_frena(rutas):
    rep = _corre_guard(_Post(
        "Barricada publicó discos entre 1983 y 1996, con giras por todo el país.",
        kind="band", title="Barricada",
    ))
    assert not rep.necesita_revision


def test_el_guard_esta_enchufado_al_camino_de_publicacion():
    """Que exista el detector no sirve de nada si nadie lo llama: esto vigila que
    siga colgado de `auto_publish_post` y que siga enrutando, no rechazando."""
    import inspect
    fuente = inspect.getsource(publishing.auto_publish_post)
    assert "sensitive_topics" in fuente
    assert "necesita_revision" in fuente
    assert "propose_for_review" in fuente
