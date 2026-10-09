"""Qué vídeo de YouTube vale como directo de UNA canción (09-10-2026)."""
from __future__ import annotations

from scripts.instagram.buscar_canciones_directo import aceptar, canciones_del_titulo

CAT = {"si te vas", "la vereda de la puerta de atras", "salir", "golfa", "extremaydura"}


def _v(titulo, dur=280, canal="Fan Rockero", desc=""):
    return {"title": titulo, "duration_s": dur, "channel_title": canal, "description": desc}


def test_un_directo_de_la_cancion_vale():
    assert aceptar(_v("Extremoduro - Si te vas (Directo Barcelona 2008)"), "Si te vas...", CAT) is None


def test_si_nombra_dos_canciones_no_vale():
    v = _v("Extremoduro en directo: Si te vas + Golfa")
    assert aceptar(v, "Si te vas...", CAT) == "el título nombra varias canciones"


def test_si_no_nombra_la_cancion_no_vale():
    assert aceptar(_v("Extremoduro directo Golfa"), "Si te vas...", CAT) == "el título no nombra la canción"


def test_un_tributo_no_vale():
    v = _v("Pedrá tributo a Extremoduro - Si te vas en directo")
    assert aceptar(v, "Si te vas...", CAT) == "tributo"


def test_un_concierto_entero_no_vale():
    assert aceptar(_v("Extremoduro Si te vas directo", dur=5400), "Si te vas...", CAT) \
        == "duración fuera de 2-12 min"


def test_tiene_que_ser_un_directo():
    assert aceptar(_v("Extremoduro - Si te vas (videoclip)"), "Si te vas...", CAT) \
        == "no dice que sea un directo"


def test_un_titulo_dentro_de_otro_no_es_otra_cancion():
    cat = {"salir", "salir de la ciudad"}
    assert canciones_del_titulo("Robe - Salir de la ciudad en directo", cat) == {"salir de la ciudad"}


def test_las_canciones_gemelas_casan_por_titulo_base():
    v = _v("Extremoduro - Extremaydura en directo (Cáceres 1997)")
    assert aceptar(v, "Extremaydura (Rock Transgresivo)", CAT) is None
