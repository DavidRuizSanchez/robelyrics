"""Una noticia del blog se escribe con su artículo.

Fixture: el post #65 tal y como estaba publicado (cartel inventado: Fito Cabrales,
Kutxi Romero, «Los Robe») y el artículo de laguiago del que salía, que no nombra a
ningún músico. Y el borrador #539, bueno, con su artículo de MariskalRock: tiene que
pasar. Si alguien toca la guarda y el #65 deja de caer, la guarda está mal.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import source_grounding as sg

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "flores_amarillas_2027.json").read_text("utf-8")
)
POST_65 = FIXTURE["post_65"]
PROP_539 = FIXTURE["prop_539"]
# Lo que tiene ficha en la web (un recorte: lo que importa al caso).
CASA = {"Plasencia", "Kutxi Romero", "Marea", "Fito Cabrales", "Fito & Fitipaldis",
        "Si te vas...", "Torre Lucía", "Material defectuoso"}


@pytest.fixture
def juez_que_no_encuentra(monkeypatch):
    """El juez contra el artículo no encuentra la frase (no hay cita literal)."""
    llamadas: list[str] = []

    def falso(frase, material):
        llamadas.append(frase)
        return {"verdict": "not_found", "source": "material", "evidence": ""}

    monkeypatch.setattr(
        "app.services.instagram.caption_guard._lo_dice_el_articulo", falso
    )
    return llamadas


def _nombres(v: sg.Veredicto) -> set[str]:
    return {h.nombre for h in v.bloqueos if h.nombre}


def test_el_cartel_inventado_del_65_cae():
    v = sg.revisar(POST_65["body_md"], POST_65["articulo"], casa=CASA, juez=False)
    assert not v.ok
    caidos = _nombres(v)
    assert "Fito Cabrales" in caidos
    assert "Kutxi Romero" in caidos
    assert "Los Robe" in caidos


def test_tener_ficha_no_pone_a_nadie_en_un_cartel():
    """Kutxi tiene ficha; en una frase de participación eso no basta."""
    v = sg.revisar(POST_65["body_md"], POST_65["articulo"], casa=CASA, juez=False)
    kutxi = [h for h in v.bloqueos if h.nombre == "Kutxi Romero"]
    assert kutxi and kutxi[0].tipo == "participacion"


def test_con_ficha_y_sin_anunciar_nada_si_se_puede_nombrar():
    cuerpo = "Kutxi Romero, de Marea, habló muchas veces de Robe en sus entrevistas."
    v = sg.revisar(cuerpo, POST_65["articulo"], casa=CASA, juez=False)
    assert v.ok, v.motivo()


def test_participacion_sin_nombres_la_juzga_el_articulo(juez_que_no_encuentra):
    v = sg.revisar(POST_65["body_md"], POST_65["articulo"], casa=CASA, juez=True)
    frases = {h.frase for h in v.bloqueos if h.tipo == "sin_respaldo"}
    assert any("compartieron escenario con Robe" in f for f in frases)


def test_el_borrador_bueno_pasa(juez_que_no_encuentra):
    v = sg.revisar(PROP_539["body_md"], PROP_539["articulo"], casa=CASA, juez=False)
    assert v.ok, v.motivo()


def test_sin_articulo_no_hay_veredicto_bueno():
    v = sg.revisar(POST_65["body_md"], "", casa=CASA)
    assert not v.ok and v.sin_articulo
    assert "sin material no hay post" in v.motivo()


def test_quitar_frases_se_lleva_el_cartel_y_deja_lo_demas():
    v = sg.revisar(POST_65["body_md"], POST_65["articulo"], casa=CASA, juez=False)
    limpio = sg.quitar_frases(POST_65["body_md"], v)
    for nombre in ("Fito Cabrales", "Kutxi", "Los Robe"):
        assert nombre not in limpio
    assert "Plasencia" in limpio


@pytest.mark.parametrize("frase,esperado", [
    ("Entre los músicos confirmados se encuentra Fito Cabrales.", ["Fito Cabrales"]),
    ("Fito Cabrales y Kutxi Romero actuarán.", ["Fito Cabrales", "Kutxi Romero"]),
    ("El respaldo de la Junta de Extremadura es firme.", ["Junta de Extremadura"]),
    ("Además, el festival contará con Los Robe.", ["Los Robe"]),
    ("Este evento busca honrar su legado.", []),
])
def test_nombres_en(frase, esperado):
    assert sg.nombres_en(frase) == esperado


def test_quitar_la_cabeza_no_convierte_un_apodo_en_robe():
    assert not sg._en_fuente("Los Robe", sg._norm("Homenaje a Robe en Plasencia"))
    assert sg._en_fuente("Festival Flores Amarillas", sg._norm("vuelve Flores Amarillas"))


def test_negar_un_anuncio_no_hay_que_respaldarlo(juez_que_no_encuentra):
    """Es lo que se le pide al redactor cuando la noticia no da cartel."""
    for frase in ("No se han anunciado los nombres de los grupos ni el orden de las actuaciones.",
                  "Aún no se ha confirmado quién actuará."):
        assert sg.revisar(frase, PROP_539["articulo"], juez=True).ok, frase
    assert juez_que_no_encuentra == []


def test_negar_no_salva_un_nombre_inventado():
    v = sg.revisar("Fito Cabrales aún no ha confirmado si actuará.", POST_65["articulo"],
                   casa=CASA, juez=False)
    assert "Fito Cabrales" in _nombres(v)


def test_lo_propio_se_puede_nombrar_pero_no_pone_a_nadie_en_un_cartel():
    """El dossier de la BD vale para escribir un nombre, no para anunciarlo."""
    propio = "[FORMACIÓN] Selu Nieto, saxo en Extremoduro."
    contexto = "En los discos de los noventa sonaba el saxo de Selu Nieto."
    assert sg.revisar(contexto, POST_65["articulo"], propio=propio, juez=False).ok
    anuncio = "Selu Nieto actuará en Flores Amarillas 2027."
    v = sg.revisar(anuncio, POST_65["articulo"], propio=propio, juez=False)
    assert "Selu Nieto" in _nombres(v)
