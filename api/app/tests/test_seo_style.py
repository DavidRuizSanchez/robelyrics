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


def test_letra_pegada_ya_no_es_canonica():
    """Hasta el 11-11-2026 «<Canción> letra: …» era el patrón del sitio (121 fichas).
    David lo descartó al ver «Plasencia Robe»: la keyword se cubre, no se pega."""
    assert st.title_pattern("Desarraigo letra: Robe explora soledad") == "antinatural"
    assert st.title_pattern("La Carrera letra: crítica social en Agila") == "antinatural"
    assert st.title_pattern("Barricada grupo: historia y legado") == "antinatural"
    assert st.title_pattern("Libertad significado en la obra de Robe") == "antinatural"
    assert st.title_pattern("Avispa Sello: Primer Hogar de Extremoduro") == "antinatural"


def test_un_determinante_delante_del_generico_no_es_keyword():
    assert st.title_pattern("Robe y La ley innata: un álbum conceptual") == "ok"
    assert st.title_pattern("Un disco de 1996 y sus canciones") == "ok"


# --- Casos reales del 11-11-2026 ---------------------------------------------
PEGADOS_PUBLICADOS = [
    ("Plasencia Robe: Cuna de Extremoduro y su legado", "Plasencia robe"),
    ("Selu Extremoduro: Su Impacto y Legado Musical", "Selu extremoduro"),
    ("El abismo significado en la obra de Robe: análisis", "El abismo significado"),
    ("Se nos lleva el aire disco: Último trabajo de Robe", "Se nos lleva el aire disco"),
    ("Segundo movimiento: Mierda de filosofía letra y análisis",
     "Segundo movimiento Mierda de filosofía letra"),
    ("La hoguera extremoduro: significado y contexto",
     "['La hoguera extremoduro', 'La hoguera el fuego la mecha extremoduro']"),
]


@pytest.mark.parametrize("title,kw", PEGADOS_PUBLICADOS)
def test_la_keyword_pegada_se_caza_con_la_keyword_de_la_pagina(title, kw):
    assert st.keyword_pegada(title, kw), title


@pytest.mark.parametrize("title,kw", [
    ("La Plasencia de Robe: cuna de Extremoduro", "Plasencia robe"),   # David
    ("Letra de Desarraigo - Extremoduro", "Desarraigo letra"),          # David
    ("La ley innata, disco de 2008", "La ley innata disco"),           # la coma corta
    ("Puta humanidad de Robe: letra y significado", "Puta humanidad Robe letra"),
    ("Uoho en Extremoduro: guitarra y producción", "Uoho extremoduro"),
    (TITLE_ORO, "Barricada grupo"),
])
def test_cubrir_la_keyword_con_naturalidad_no_es_pegarla(title, kw):
    assert not st.keyword_pegada(title, kw), title


def test_una_keyword_de_una_palabra_nunca_esta_pegada():
    assert not st.keyword_pegada("Extremoduro: origen, género y evolución", "Extremoduro")


def test_formulas_vacias():
    assert "explora" in st.formulas_vacias("Menamoro letra: Robe explora el amor y la libertad")
    assert "su impacto" in st.formulas_vacias("Selu Extremoduro: Su Impacto y Legado Musical")
    assert not st.formulas_vacias(TITLE_ORO)


def test_title_case_tras_los_dos_puntos_bloquea():
    v = _title("Barricada: Miembros, historia y legado del grupo de rock español")
    assert not v.ok
    assert any("Title Case" in m for m in v.motivos)


def test_un_nombre_propio_tras_los_dos_puntos_no_es_title_case():
    """«El Drogas» sale capitalizado en el cuerpo: es un nombre, no Title Case."""
    assert "El Drogas" in CUERPO or "Drogas" in CUERPO
    assert not st.mayusculas_indebidas("Barricada: El Drogas y Piedrafita", CUERPO)


def test_sin_fuentes_no_se_juzga_la_capitalizacion():
    assert st.mayusculas_indebidas("Barricada: Miembros e Historia", "") == []


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


def test_un_nombre_en_enlace_o_cursiva_no_es_title_case():
    """Medido en prod el 11-11-2026: sin saltarse el marcado, «Extremoduro» salía
    como Title Case en «El tejado en la obra de Extremoduro y Robe»."""
    cuerpo = ("Lo cantó Robe con [Extremoduro](/extremoduro) en *Yo, minoría absoluta* "
              "y en «Agila».")
    assert not st.mayusculas_indebidas("El tejado en la obra de Extremoduro y Robe",
                                       cuerpo, nombres="El tejado")
    assert not st.mayusculas_indebidas("Gira 2002 de Yo, minoría absoluta: en vivo", cuerpo)
    assert st.mayusculas_indebidas("Agila: La Metáfora", cuerpo) == ["La", "Metáfora"]


@pytest.mark.parametrize("modelo,esperado", [
    ("«Perro Callejero», de Extremoduro: letra y colaboración de Rosendo",
     "«Perro Callejero», de Extremoduro: letra y colaboración de Rosendo"),
    ("Pasión: el sello que publicó «Somos unos Animales»",
     "Pasión: el sello que publicó «Somos unos Animales»"),
    ("«Barricada: miembros e historia»", "Barricada: miembros e historia"),
])
def test_solo_se_quitan_las_comillas_que_envuelven_todo(modelo, esperado):
    """Medido el 11-11-2026: un strip de «» publicó 8 titles con la comilla rota."""
    assert st.quitar_comillas_envolventes(modelo) == esperado


def test_comillas_desparejadas_bloquean():
    v = _title("Barricada», de Pamplona: miembros, historia y legado")
    assert any("desparejadas" in m for m in v.motivos)


def test_un_nombre_de_casa_que_la_pagina_no_nombra_bloquea():
    """11-11-2026: «Álvaro Rodríguez Barroso: de extremoduro a CIRA» sobre un
    músico de la banda de Robe. El cuerpo no nombra a Extremoduro ni una vez."""
    cuerpo = ("Álvaro Rodríguez Barroso se unió a la banda de Robe en 2013 como teclista. "
              "Produjo [Mayéutica](https://entreinteriores.com/robe/mayeutica), enlazada "
              "desde [la discografía](https://entreinteriores.com/extremoduro). "
              "En 2019 publicó CIRA.")
    v = st.title_verdict("Álvaro Rodríguez Barroso: de extremoduro a CIRA", body_md=cuerpo,
                         subject="Álvaro Rodríguez Barroso", entity_type="person")
    assert any("mayúscula" in m for m in v.motivos)
    assert any("la página no" in m for m in v.motivos)
    ok = st.title_verdict("Álvaro Rodríguez Barroso: teclista y productor de Robe",
                          body_md=cuerpo, subject="Álvaro Rodríguez Barroso",
                          entity_type="person")
    assert ok.ok, ok.motivos
