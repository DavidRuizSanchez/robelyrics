"""Desactivar keywords y recalcular la objetivo (petición de David, 19-10-2026)."""
from __future__ import annotations

import pytest

from app.services import content_merge as cm


class _Prop:
    def __init__(self):
        self.kind = "evergreen"
        self.target_keyword = "que genero es extremoduro"
        self.target_keyword_slug = "que-genero-es-extremoduro"
        self.search_volume = 99
        self.content_key = "evergreen:que-genero-es-extremoduro"
        self.keywords = [
            {"keyword": "que genero es extremoduro", "volume": 99},
            {"keyword": "extremoduro cancion de amor", "volume": 110},
            {"keyword": "extremoduro necesito droga y amor", "volume": 260},
        ]


def test_desactivar_una_keyword_la_tacha_sin_borrarla():
    p = _Prop()
    cm.excluir_keywords(p, ["extremoduro cancion de amor"])
    kws = {k["keyword"]: k for k in p.keywords}
    assert kws["extremoduro cancion de amor"]["excluded"] is True
    assert len(p.keywords) == 3
    assert p.target_keyword == "que genero es extremoduro"   # la objetivo sigue activa


def test_si_se_desactiva_la_objetivo_pasa_a_la_activa_de_mas_volumen():
    p = _Prop()
    cm.excluir_keywords(p, ["que genero es extremoduro"])
    assert p.target_keyword == "extremoduro necesito droga y amor"
    assert p.content_key == "evergreen:extremoduro-necesito-droga-y-amor"
    assert p.search_volume == 260


def test_reactivar_es_volver_a_pulsar():
    p = _Prop()
    cm.excluir_keywords(p, ["extremoduro cancion de amor"])
    cm.excluir_keywords(p, [])
    assert not any(k.get("excluded") for k in p.keywords)


def test_no_se_pueden_desactivar_todas():
    p = _Prop()
    with pytest.raises(cm.MergeError):
        cm.excluir_keywords(p, [k["keyword"] for k in p.keywords])


def test_una_keyword_fundida_no_se_reactiva_desde_el_panel():
    p = _Prop()
    p.keywords[2].update({"excluded": True, "merged": "/extremoduro/x/necesito"})
    cm.excluir_keywords(p, [])
    assert p.keywords[2]["excluded"] is True
