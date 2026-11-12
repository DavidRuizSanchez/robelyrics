"""La formación en Instagram: quién tocaba en cada disco (12-11-2026).

Dos casos publicados: el #297 («Somos unos animales (1991)… con Miguel Ferreras al
bajo»; Ferreras entró en 1993) y la slide de «La Dualidad de 'De Acero'» (Uoho en
«Deltoya», 1992; Uoho entra en 1996). Las fechas son las de `band_memberships`.
"""
from __future__ import annotations

from app.services.instagram.gate_final import Disco, Pertenencia, era_a_anios, revisar

P = [
    Pertenencia(("miguel ferreras", "ferreras"), "extremoduro", 1993, 1994),
    Pertenencia(("carlos jimenez", "el sucio"), "extremoduro", 1990, 1993),
    Pertenencia(("inaki anton", "uoho"), "extremoduro", 1996, 2014),
    Pertenencia(("roberto iniesta", "robe"), "extremoduro", 1987, 2019),
    Pertenencia(("miguel colino",), "extremoduro", 2001, 2014),
]
D = [
    Disco("somos unos animales", "extremoduro", 1991),
    Disco("deltoya", "extremoduro", 1992),
    Disco("agila", "extremoduro", 1996),
    Disco("rock transgresivo", "extremoduro", 1994),
    Disco("pedra", "extremoduro", 1995, frozenset({"inaki anton", "uoho"})),
]

CAPTION_297 = """Lo dijo mejor «Quemando Tus Recuerdos» que cualquier explicación.

«Quemando Tus Recuerdos» · Extremoduro · Somos unos animales (1991)

La canción se grabó con Miguel Ferreras al bajo, parte de la formación catalana de Extremoduro.

¿Dónde estabas la primera vez que escuchaste esto?"""


def _bloqueos(texto, **kw):
    return revisar(caption=texto, formacion=(P, D), **kw).bloqueos


def test_el_297_cae():
    b = _bloqueos(CAPTION_297)
    assert b and "miguel ferreras" in b[0] and "1991" in b[0]


def test_uoho_en_deltoya_cae():
    slide = "En «Deltoya», la formación incluía a Robe y a Iñaki 'Uoho' Antón."
    b = revisar(caption="Un carrusel.", slides=[slide], formacion=(P, D)).bloqueos
    assert b and "uoho" in b[0].lower()


def test_lo_cierto_pasa():
    assert not _bloqueos("Uoho a la guitarra en «Agila» (1996), con Robe a la voz.")
    assert not _bloqueos("En «Somos unos animales» (1991) el Sucio tocaba el bajo.")


def test_un_colaborador_no_se_juzga():
    # Rosendo no tiene pertenencia: no hay fechas contra las que comparar.
    assert not _bloqueos("Rosendo a la guitarra en «Deltoya» (1992).")


def test_sin_verbo_de_tocar_no_salta():
    assert not _bloqueos("Ferreras recuerda «Somos unos animales» (1991) como un disco clave.")


def test_el_invitado_con_fuente_pasa():
    # #349: Uoho grabó «Pedrá» (1995) siendo aún de Platero; entra en 1996.
    assert not _bloqueos("En «Pedrá» (1995), Extremoduro grabó con Uoho a la guitarra.")


def test_un_anio_suelto_no_es_un_disco():
    # #68: el año del nacimiento no sitúa a nadie en un disco.
    assert not _bloqueos("Iñaki Antón (Bilbao, 1964) es guitarrista de Extremoduro.")


def test_la_formacion_de_otro_grupo_no_se_juzga():
    # #228: la cabecera habla de un disco de Extremoduro, la frase de otro grupo.
    texto = ("«Golfa» · Extremoduro · «Canciones prohibidas» (1998)\n\n"
             "La formación inicial incluyó a Miguel Colino en el bajo y a Polako en la batería.")
    assert not _bloqueos(texto)


def test_el_oficio_sin_disco_en_la_frase_no_salta():
    # #228 (segunda frase): describe al bajista, no lo pone en el disco de la cabecera.
    texto = ("«Golfa» · Extremoduro · «Canciones prohibidas» (1998)\n\n"
             "Miguel Colino, nacido en Portugalete en 1966, es un bajista clave entre "
             "Fito & Fitipaldis y Extremoduro.")
    assert not _bloqueos(texto)


def test_el_oficio_con_el_disco_en_la_frase_si_salta():
    assert _bloqueos("Ferreras fue el bajista de «Somos unos animales» (1991).")


def test_el_estilo_no_es_el_disco():
    # «rock transgresivo» sin citar como disco no fija el año 1994.
    assert not _bloqueos("Ferreras tocaba rock transgresivo en Rubí en 1993.")


def test_era_a_anios():
    assert era_a_anios("1993-1994") == (1993, 1994)
    assert era_a_anios("1987") == (1987, 1987)
    assert era_a_anios("2013", actual=True) == (2013, 9999)
    assert era_a_anios(None) is None
