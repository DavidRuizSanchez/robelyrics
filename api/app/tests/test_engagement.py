"""Tests del score de engagement → tier (núcleo puro, sin BD)."""
from __future__ import annotations

from app.services import engagement as eng


def test_tema_pobre_es_standard():
    score, tier = eng.score_from_signals(volume=5, graph_degree=1, fan_sources=0)
    assert tier == eng.TIER_STANDARD
    assert score < 40


def test_tema_rico_y_buscado_es_flagship():
    score, tier = eng.score_from_signals(
        volume=600, graph_degree=18, fan_sources=12, related_videos=3
    )
    assert tier == eng.TIER_FLAGSHIP
    assert score >= 65


def test_intermedio_es_premium():
    score, tier = eng.score_from_signals(volume=90, graph_degree=8, fan_sources=5)
    assert tier == eng.TIER_PREMIUM
    assert 40 <= score < 65


def test_score_monotono_en_volumen():
    lo, _ = eng.score_from_signals(volume=10, graph_degree=5, fan_sources=3)
    hi, _ = eng.score_from_signals(volume=500, graph_degree=5, fan_sources=3)
    assert hi > lo


def test_score_acotado_0_100():
    score, _ = eng.score_from_signals(
        volume=99999, graph_degree=999, fan_sources=999, related_videos=99
    )
    assert 0 <= score <= 100


# --- Política content_tier ---------------------------------------------------
def test_noticia_respeta_su_tier():
    assert eng.content_tier("news", 10, "standard") == "standard"


def test_no_noticia_tiene_suelo_flagship():
    # Un evergreen flojo NO baja de flagship (calidad por defecto).
    assert eng.content_tier("evergreen", 20, "standard", "song") == "flagship"
    assert eng.content_tier("spotlight", 30, "premium", "song") == "flagship"


def test_tematica_alto_engagement_es_cornerstone():
    assert eng.content_tier("evergreen", 70, "flagship", "theme") == "cornerstone"
    assert eng.content_tier("evergreen", 60, "premium", "concept") == "cornerstone"


def test_tematica_bajo_engagement_no_llega_a_cornerstone():
    assert eng.content_tier("evergreen", 30, "standard", "theme") == "flagship"


def test_amplitud_de_tema_sube_el_score():
    # Un tema que atraviesa medio cancionero es cornerstone-eligible aunque su
    # volumen de búsqueda directo sea nulo.
    ancho, ta = eng.score_from_signals(volume=None, graph_degree=2, fan_sources=8, theme_reach=20)
    estrecho, te = eng.score_from_signals(volume=None, graph_degree=2, fan_sources=8, theme_reach=2)
    assert ancho > estrecho
    assert eng.content_tier("evergreen", ancho, ta, "theme") == "cornerstone"
