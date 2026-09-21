"""El criterio editorial del title y la description.

Lo que se blinda aquí es una decisión de David del 22-09-2026, tomada al rechazar
el primer borrador que produjo el circuito para `/grupos/barricada`:

  - **El title representa el contenido de la página.** Se optimiza para el término
    principal y, si además se puede hilar otro, bien; si no se puede, NO SE FUERZA.
    Nunca se cambia el sentido de un title para colocar una keyword.
  - **La description no es un elemento de ranking: es lo que capta el clic.**

Los textos que él escribió a mano están congelados en este fichero junto al cuerpo
real de la página (`fixtures/barricada_publicado.md`). Son el criterio de aceptación:
si alguien toca las guardas y el texto de David deja de pasar, la guarda está mal,
no el texto. Eso ya pasó dos veces —el tope de 60 caracteres le comía «español» al
title, y la anti-invención tumbaba su description por las palabras «todos», «datos»
y «mítico»—, y por eso estos tests existen.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services import seo_style as st

CUERPO = (Path(__file__).parent / "fixtures" / "barricada_publicado.md").read_text(
    encoding="utf-8"
)

# --- Los textos de David, tal cual los escribió -------------------------------
TITLE_ORO = "Barricada: miembros, historia y legado del grupo de rock español"
DESC_ORO = ("Conoce todos los datos de este grupo mítico de rock español y su "
            "relación con Extremoduro: miembros, historia y legado.")
# --- Y los que rechazó --------------------------------------------------------
TITLE_PUBLICADO = "Barricada grupo: historia y legado en el rock español"
TITLE_RECHAZADO = "Miembros y origen de Barricada: El Drogas y Piedrafita"
DESC_RECHAZADA = ("Barricada, grupo musical de Pamplona. Miembros clave: El Drogas "
                  "y Alfredo Piedrafita. Influencia en bandas como Extremoduro.")
DESC_PUBLICADA = ("Barricada, grupo clave del rock español, influyó en bandas como "
                  "Extremoduro y dejó un legado perdurable tras su disolución en 2013.")


def _title(t: str, **kw):
    return st.title_verdict(t, body_md=CUERPO, subject="Barricada",
                            entity_type="band", **kw)


def _desc(d: str, **kw):
    return st.desc_verdict(d, title=TITLE_ORO, body_md=CUERPO, entity_type="band", **kw)


# --------------------------------------------------------------------------- #
# El title
# --------------------------------------------------------------------------- #
def test_el_title_que_escribio_david_pasa():
    """Criterio de aceptación. Tiene 64 caracteres: el tope de 60 le comía «español»."""
    v = _title(TITLE_ORO, target_keyword="Barricada grupo")
    assert v.ok, v.motivos
    assert len(TITLE_ORO) == 64


def test_no_se_cambia_el_sentido_del_title_para_colocar_un_termino():
    """La página va del grupo; ese title prometía una página sobre sus miembros."""
    v = _title(TITLE_RECHAZADO)
    assert not v.ok
    assert any("promete otra cosa" in m for m in v.motivos)


def test_la_keyword_no_se_pega_en_crudo():
    """«Barricada grupo» no es español, y sale de ordenarle al motor que pegue la
    keyword al inicio. Es el title que hay publicado."""
    v = _title(TITLE_PUBLICADO)
    assert not v.ok
    assert any("en crudo" in m for m in v.motivos)


def test_el_patron_canonico_de_cancion_no_se_veta():
    """Las 99 fichas de canción usan «<Canción> letra: …» y se quedan como están:
    es como se busca. Vetar «letra» junto a «grupo» es el error fácil de cometer
    aquí, y encolaría 99 páginas que funcionan.

    Los ejemplos llevan «letra» PEGADA al nombre propio, que es la forma real que
    tienen en producción: con «… de Extremoduro: letra y significado» el test
    estaría verde aunque alguien vetara la palabra, porque ahí no va pegada.
    """
    assert st.title_pattern("Desarraigo letra: Robe explora soledad") == "canonical"
    assert st.title_pattern("La Carrera letra: crítica social en Agila") == "canonical"
    assert st.title_pattern("Barricada grupo: historia y legado") == "antinatural"
    assert st.title_pattern("Libertad significado en la obra de Robe") == "antinatural"


def test_el_title_no_puede_prometer_lo_que_la_pagina_no_tiene():
    v = _title("Barricada: miembros, historia y sus giras por Japón")
    assert not v.ok
    assert any("Japón" in m or "japón" in m.lower() for m in v.motivos)


def test_una_faceta_de_genero_no_necesita_estar_escrita_en_el_cuerpo():
    """Una ficha de grupo cuenta su historia aunque no escriba la palabra
    «historia»: la de Barricada la cuenta bajo «Origen y evolución». Sin esta
    exención, un title correcto se rechazaría por enumerar la faceta que la página
    sí cubre, pero con otras palabras.

    El cuerpo del test es sintético a propósito: el de Barricada sí contiene
    «historia» en otro contexto («celebra la historia compartida»), así que con él
    este test estaría verde por el motivo equivocado.
    """
    cuerpo = ("## Origen y evolución\n\nLa banda nació en 1982 en Pamplona y se "
              "separó en 2013 tras quince discos.\n")
    assert "histori" not in st.flatten(cuerpo)
    v = st.title_verdict("Los Suaves: historia del grupo de rock español",
                         body_md=cuerpo, subject="Los Suaves", entity_type="band")
    assert v.ok, v.motivos
    # Y sin el tipo que la legitima, la misma faceta se rechaza.
    sin_tipo = st.title_verdict("Los Suaves: historia del grupo de rock español",
                                body_md=cuerpo, subject="Los Suaves", entity_type="")
    assert not sin_tipo.ok


def test_el_termino_principal_se_cubre_sin_pegarlo():
    """Cubrir no es contener: el title de David no dice «Barricada grupo» en ningún
    sitio y sin embargo lo cubre entero."""
    assert st.cubre_termino(TITLE_ORO, "Barricada grupo")
    assert "Barricada grupo" not in TITLE_ORO


def test_si_el_termino_no_cabe_natural_no_se_fuerza():
    """David: «si no se puede, no se fuerza». Avisa, pero no bloquea."""
    v = _title("Barricada: miembros e historia", target_keyword="barricada discografía")
    assert v.ok
    assert any("término principal" in a for a in v.avisos)


def test_un_title_que_no_cabe_se_rechaza_pero_nunca_se_corta():
    largo = "Barricada: miembros, historia, legado y discografía del grupo de rock español"
    assert not _title(largo).ok
    assert st.fit_or_none(largo, st.TITLE_HARD_MAX) is None
    assert st.fit_or_none(TITLE_ORO, st.TITLE_HARD_MAX) == TITLE_ORO


# --------------------------------------------------------------------------- #
# La description
# --------------------------------------------------------------------------- #
def test_la_description_que_escribio_david_pasa():
    """Tiene 119 caracteres: el mínimo de 125 que pedía el prompt la excluía."""
    v = _desc(DESC_ORO)
    assert v.ok, v.motivos
    assert len(DESC_ORO) == 119


def test_la_description_telegrafica_se_rechaza():
    """Tres sintagmas sin un solo verbo no captan a nadie."""
    v = _desc(DESC_RECHAZADA)
    assert not v.ok
    assert any("telegráfica" in m for m in v.motivos)


def test_lo_telegrafico_se_pondera_por_palabras_y_no_por_frases():
    """La description de David tiene DOS trozos y uno va sin verbo («miembros,
    historia y legado»). Contando trozos daría 0,50 —a cinco centésimas del umbral,
    o sea viva de milagro—; contando palabras da 0,20, porque ese trozo son cuatro
    palabras de veinte. La ponderación es lo que separa un cierre enumerativo
    legítimo de una description que son solo sintagmas.
    """
    assert st.ratio_telegrafico(DESC_ORO) == pytest.approx(0.20, abs=0.01)
    assert st.ratio_telegrafico(DESC_RECHAZADA) == 1.0
    # Y el cierre enumerativo por sí solo no la condena.
    assert st.ratio_telegrafico(
        "Descubre qué cuenta este disco y por qué marcó a una generación: letras, "
        "grabación y significado."
    ) < 0.55


def test_un_resumen_correcto_pasa_pero_se_avisa():
    """La description publicada tiene verbos, cabe y cita el diferencial: ninguna
    regla razonable la caza. Y aun así es un RESUMEN, no una promesa. Eso se avisa,
    no se bloquea: lo demás vive en el prompt y en los ejemplos."""
    v = _desc(DESC_PUBLICADA)
    assert v.ok
    assert any("resumen" in a for a in v.avisos)


def test_una_palabra_comun_no_tumba_una_description_correcta():
    """No-regresión: la primera versión de la guarda tumbó el texto de David por
    «todos», «datos» y «mítico». Una guarda que rechaza lo bueno acaba apagada."""
    assert _desc(DESC_ORO).ok


def test_un_dato_inventado_en_la_description_se_rechaza():
    mala = ("Conoce todo sobre este grupo mítico de rock español, fundado en 1979 "
            "por Rosendo, y su relación con Extremoduro: miembros e historia.")
    v = _desc(mala)
    assert not v.ok
    assert any("1979" in m and "Rosendo" in m for m in v.motivos)


def test_se_avisa_cuando_el_angulo_propio_esta_y_no_se_usa():
    """La relación con Extremoduro es lo que este sitio tiene y los demás no."""
    v = _desc("Conoce la historia de este grupo mítico de rock español: sus miembros, "
              "sus discos y el legado que dejó cuando se separó.")
    assert v.ok
    assert any("Extremoduro" in a for a in v.avisos)


# --------------------------------------------------------------------------- #
# Capitalización
# --------------------------------------------------------------------------- #
def test_la_capitalizacion_no_baja_un_nombre_propio():
    """`fuentes` tiene que traer el cuerpo: con `fuentes=""` esto escribe «el drogas»."""
    entrada = "Miembros de Barricada: El Drogas y Alfredo Piedrafita"
    assert st.spanish_case(entrada, CUERPO) == entrada
    assert "el drogas" in st.spanish_case(entrada, "").lower()


def test_la_capitalizacion_baja_el_title_case_ingles():
    assert st.spanish_case("Barricada: Historia y Legado del Grupo", "Barricada") == \
        "Barricada: Historia y legado del grupo"


@pytest.mark.parametrize("texto", [TITLE_ORO, DESC_ORO])
def test_los_textos_de_david_sobreviven_a_la_capitalizacion(texto):
    assert st.spanish_case(texto, CUERPO) == texto
