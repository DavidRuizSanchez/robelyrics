"""El texto que se quema dentro del clip: que diga algo y que QUEPA.

Antes era el título del post, que ni servía de rótulo ni entraba: medido, «Robe,
desde el escenario — La Cubierta, Leganés, 09-10-1999» ocupa 1622 px con la
fuente que usa ffmpeg y el hueco son 1044, así que se recortaba por los dos
lados a la vez (el texto va centrado).
"""
from __future__ import annotations

import pytest

from app.services.instagram import rotulo
from app.services.instagram import video_clips as vc


# --------------------------------------------------------------------------- #
# Que quepa
# --------------------------------------------------------------------------- #
def test_el_rotulo_que_se_publicaba_no_cabia():
    """La medida que destapó el problema."""
    largo = "Robe, desde el escenario — La Cubierta, Leganés, 09-10-1999"
    assert vc.ancho_texto(largo, 52) > vc.ANCHO_UTIL


def test_un_texto_largo_baja_de_tamano_hasta_entrar():
    largo = "«Por encima del bien y del mal» · Barcelona · 2022"
    texto, tamano = vc._encoger(largo, vc.DATO_PX, vc.DATO_PX_MIN)
    assert texto == largo, "no se recorta si basta con encoger"
    assert vc.ancho_texto(texto, tamano) <= vc.ANCHO_UTIL


def test_si_no_cabe_ni_al_minimo_se_recorta_por_palabra():
    """Partir una palabra por la mitad se lee peor que perder la última."""
    imposible = "palabras " * 40
    texto, tamano = vc._encoger(imposible, vc.DATO_PX, vc.DATO_PX_MIN)
    assert vc.ancho_texto(texto, tamano) <= vc.ANCHO_UTIL
    assert texto.endswith("…")
    assert "palabra…" not in texto, "no se corta una palabra por la mitad"


def test_los_emojis_se_quitan():
    """DejaVu Sans no los tiene: se dibujarían como una caja vacía."""
    assert vc.sin_emojis("¡Qué pasada! 🎸🔥") == "¡Qué pasada!"


# --------------------------------------------------------------------------- #
# Que el gancho sea un gancho, no un titular
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("malo,por_que", [
    ("¡Qué pasada! 🔥", "emoji"),
    ("¡Menudo 1999!", "cifra"),
    ("¡Cómo sonaba Barcelona!", "nombre propio"),
    ("¡Una exclamación larguísima que no cabe de ninguna manera!", "largo"),
    ("Un canto a la libertad", "molde"),
])
def test_un_gancho_que_no_vale_se_rechaza(malo, por_que):
    ok, motivo = rotulo._vale(malo)
    assert not ok, f"debería rechazarse por {por_que}: {motivo}"


@pytest.mark.parametrize("bueno", [
    "¡Qué pasada!", "¡Menuda locura!", "¡Pelos de punta!", "¡Qué momento!",
])
def test_los_ganchos_del_estilo_que_pidio_david_pasan(bueno):
    ok, motivo = rotulo._vale(bueno)
    assert ok, motivo


def test_sin_modelo_se_cae_al_banco_y_es_estable(monkeypatch):
    """El mismo clip da SIEMPRE el mismo rótulo: re-preparar no lo cambia."""
    import app.services.news_research as nr

    def _revienta(*a, **k):
        raise RuntimeError("sin red")

    monkeypatch.setattr(nr, "_json", _revienta)
    uno = rotulo.gancho("estribillo", "Standby", "vid:100")
    otro = rotulo.gancho("estribillo", "Standby", "vid:100")
    assert uno == otro
    assert rotulo._vale(uno)[0]


def test_cada_clip_tiene_su_gancho(monkeypatch):
    import app.services.news_research as nr

    monkeypatch.setattr(nr, "_json", lambda *a, **k: {})
    ganchos = {rotulo.gancho("estribillo", "X", f"vid:{i}") for i in range(12)}
    assert len(ganchos) > 1, "no puede salir siempre el mismo"


# --------------------------------------------------------------------------- #
# Las dos líneas
# --------------------------------------------------------------------------- #
def test_robe_hablando_no_lleva_gancho_ni_cita_lo_que_dice():
    """La transcripción de un directo está garbleada: no se cita."""
    texto = rotulo.componer(
        tipo="habla", cancion=None, lugar="La Cubierta, Leganés",
        cuando="9 de octubre de 1999", clave="v:1",
    )
    assert texto == "La Cubierta, Leganés\n9 de octubre de 1999"
    assert "¡" not in texto


def test_un_estribillo_lleva_gancho_arriba_y_el_dato_abajo(monkeypatch):
    import app.services.news_research as nr

    monkeypatch.setattr(nr, "_json", lambda *a, **k: {})
    texto = rotulo.componer(
        tipo="estribillo", cancion="Si te vas...", lugar="Barcelona",
        cuando="2022", clave="v:2",
    )
    arriba, abajo = texto.split("\n")
    assert arriba.startswith("¡")
    assert "«Si te vas...»" in abajo
    assert "Barcelona" in abajo


def test_sin_cancion_se_usa_el_verso_de_nuestra_letra(monkeypatch):
    import app.services.news_research as nr

    monkeypatch.setattr(nr, "_json", lambda *a, **k: {})
    texto = rotulo.componer(
        tipo="estribillo", cancion=None, verso="Dejo las ventanas sin cerrar",
        lugar=None, cuando=None, clave="v:3",
    )
    assert "«Dejo las ventanas sin cerrar»" in texto
