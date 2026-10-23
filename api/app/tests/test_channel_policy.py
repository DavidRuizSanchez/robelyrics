"""Política de canales: la de Instagram no cambia, la del corpus es otra.

Los nombres de canal son reales o tienen la forma de los reales (los de los
tests de clips, el canal «Robe» que publica los directos de Mayéutica).
"""
from __future__ import annotations

import pytest

from app.services import channel_policy as cp
from app.services.instagram import video_clips as vc

# La lista de `video_clips.CANALES_VETADOS` tal y como estaba antes de moverla.
# Si alguien la toca en `channel_policy`, Instagram cambia de comportamiento y
# este test lo dice.
_LISTA_CLIPS_ANTERIOR = (
    "reaccion", "reacción", "reacts", "reaction", "reacciona",
    "oficial", "official", "vevo", " - topic", "records", "discos",
    "warner", "sony music", "universal music", "dro east west",
)


def test_instagram_sigue_con_la_misma_politica():
    assert cp.CANALES_VETADOS == _LISTA_CLIPS_ANTERIOR
    assert vc.canal_vetado is cp.canal_vetado
    assert vc.canal_sensible is cp.canal_sensible


@pytest.mark.parametrize("canal", [
    "Robe", "Extremoduro", "Extremoduro Oficial", "Robe Iniesta Official",
    "Warner Music Spain", "DRO East West",
])
def test_lo_oficial_no_se_republica_pero_si_se_transcribe(canal):
    assert cp.canal_vetado(canal) is not None
    assert cp.canal_vetado(canal, modo="corpus") is None


@pytest.mark.parametrize("canal", [
    "Leo Reaccion", "Reacts Rock", "Robe - Topic", "ExtremoduroVEVO",
    "Pedrá Tributo a Extremoduro", "Karaoke Rock Español",
])
def test_reacciones_tributos_y_solo_musica_caen_tambien_en_el_corpus(canal):
    assert cp.canal_vetado(canal, modo="corpus") is not None


@pytest.mark.parametrize("canal", ["juancaraes", "Tesônica", "Extremoduro Directos", "RTVE"])
def test_fans_analistas_y_medios_valen_en_los_dos_modos(canal):
    assert cp.canal_vetado(canal) is None
    assert cp.canal_vetado(canal, modo="corpus") is None


@pytest.mark.parametrize("canal,oficial", [
    ("Robe", True), ("Extremoduro Oficial", True), ("Robe Iniesta Official", True),
    ("Extremoduro Directos", False), ("Robe y yo", False), ("juancaraes", False),
])
def test_canal_oficial(canal, oficial):
    assert cp.es_canal_oficial(canal) is oficial
