"""Hero atómico: url y crédito viajan SIEMPRE juntos (nunca desincronizados).

Regresión del bug de Rosendo: un script escribía hero_image_url nuevo pero dejaba
hero_image_attribution/source viejos → foto de X con el crédito de Y.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.hero_io import apply_hero, read_hero

_FULL = {
    "url": "https://cdn/x.jpg", "alt": "una foto", "attribution": "Autor · CC",
    "license": "CC BY", "source": "https://commons/File:x.jpg",
}


def _blank():
    return SimpleNamespace(
        hero_image_url=None, hero_image_alt=None, hero_image_attribution=None,
        hero_image_license=None, hero_image_source_url=None,
    )


def test_apply_escribe_los_cinco_campos():
    o = _blank()
    apply_hero(o, _FULL)
    assert o.hero_image_url == _FULL["url"]
    assert o.hero_image_alt == _FULL["alt"]
    assert o.hero_image_attribution == _FULL["attribution"]
    assert o.hero_image_license == _FULL["license"]
    assert o.hero_image_source_url == _FULL["source"]


def test_apply_none_limpia_todo():
    o = _blank()
    apply_hero(o, _FULL)
    apply_hero(o, None)
    assert read_hero(o) is None
    assert o.hero_image_attribution is None
    assert o.hero_image_source_url is None


def test_read_round_trip():
    src = _blank()
    apply_hero(src, _FULL)
    dst = _blank()
    apply_hero(dst, read_hero(src))  # copiar el paquete a otro objeto
    assert read_hero(dst) == _FULL


def test_no_desincronizacion_al_sustituir_imagen():
    # Post viejo con la foto e crédito de Robe.
    post = _blank()
    apply_hero(post, {"url": "robe.jpg", "alt": "Robe", "attribution": "Robe · CC",
                      "license": "CC", "source": "robe_src"})
    # Propuesta nueva con OTRA imagen (y su propio crédito).
    prop = _blank()
    apply_hero(prop, {"url": "rosendo.jpg", "alt": "Rosendo", "attribution": "Rosendo · CC",
                      "license": "CC", "source": "rosendo_src"})
    # Al arrastrar el hero (como hace regen_pending) se aplica el PAQUETE ENTERO.
    apply_hero(post, read_hero(prop))
    # El crédito ya NO es el de Robe: viaja con la imagen.
    assert post.hero_image_url == "rosendo.jpg"
    assert post.hero_image_attribution == "Rosendo · CC"
    assert post.hero_image_source_url == "rosendo_src"
