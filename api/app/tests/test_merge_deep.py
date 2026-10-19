"""La fusión monta la página sin tocar lo que no declara tocar, y sin perder lo que posiciona."""
from __future__ import annotations

from app.services import ranking_guard as rg
from scripts.seo import merge_deep as md

CUERPO = """Extremoduro fue el grupo de Robe, nacido en Plasencia en 1987.

## Los primeros años

Rock transgresivo y maquetas grabadas con lo justo.

## La etapa de Uoho

Iñaki «Uoho» Antón entra en la banda y cambia el sonido.

## El final

La banda se disolvió en 2019.
"""

PROTEGIDAS = [
    {"query": "extremoduro primeros años", "impressions": 40, "clicks": 1, "position": 6.0},
    {"query": "uoho extremoduro", "impressions": 25, "clicks": 0, "position": 9.0},
]


def _seccion(h: str, texto: str = "Hechos del material.") -> dict:
    return {"heading": h, "texto": f"## {h}\n\n{texto}"}


def test_trocear_y_unir_no_cambian_nada():
    assert md.unir(md.trocear(CUERPO)) == CUERPO


def test_lo_que_no_se_toca_queda_identico_byte_a_byte():
    ops = md.Operaciones(inserts=[{"after": "La etapa de Uoho", **_seccion("La formación")}])
    despues = md.aplicar(CUERPO, ops)
    for b in md.trocear(CUERPO):
        assert b.texto in despues
    assert md.secciones_conservadas(CUERPO, despues, ops) == []


def test_la_seccion_nueva_va_donde_encaja_no_al_final():
    ops = md.Operaciones(inserts=[{"after": "La etapa de Uoho", **_seccion("La formación")}])
    heads = [b.heading for b in md.trocear(md.aplicar(CUERPO, ops))]
    assert heads == [None, "Los primeros años", "La etapa de Uoho", "La formación", "El final"]


def test_tras_la_intro_y_varias_tras_el_mismo_heading_en_orden():
    ops = md.Operaciones(inserts=[
        {"after": md.INTRO, **_seccion("Quiénes eran")},
        {"after": "El final", **_seccion("Uno")},
        {"after": "El final", **_seccion("Dos")},
    ])
    heads = [b.heading for b in md.trocear(md.aplicar(CUERPO, ops))]
    assert heads == [None, "Quiénes eran", "Los primeros años", "La etapa de Uoho",
                     "El final", "Uno", "Dos"]


def test_un_rename_no_deja_huerfana_la_insercion_que_iba_tras_el():
    ops = md.Operaciones(
        inserts=[{"after": "La etapa de Uoho", **_seccion("La formación")}],
        renames=[{"old": "La etapa de Uoho", "new": "La etapa de Uoho en Extremoduro"}],
    )
    despues = md.aplicar(CUERPO, ops)
    heads = [b.heading for b in md.trocear(despues)]
    assert heads.index("La formación") == heads.index("La etapa de Uoho en Extremoduro") + 1
    # El cuerpo de la sección renombrada sigue entero.
    assert "Iñaki «Uoho» Antón entra en la banda y cambia el sonido." in despues
    assert md.secciones_conservadas(CUERPO, despues, ops) == []


def test_un_puente_solo_anade_al_final_de_la_seccion():
    ops = md.Operaciones(puentes=[{"after": "Los primeros años", "texto": "Y llegó Uoho."}])
    despues = md.aplicar(CUERPO, ops)
    assert "Rock transgresivo y maquetas grabadas con lo justo.\n\nY llegó Uoho." in despues
    assert md.secciones_conservadas(CUERPO, despues, ops) == []


def test_se_detecta_una_seccion_perdida():
    roto = CUERPO.replace("La banda se disolvió en 2019.", "La banda se disolvió.")
    assert md.secciones_conservadas(CUERPO, roto, md.Operaciones()) == ["El final"]


def test_cobertura_de_heading_se_mide_contra_lo_que_cubria_el_viejo():
    protegidas = [{"query": "etapa uoho", "impressions": 30, "clicks": 1, "position": 5.0}]
    assert not rg.renombre_permitido("La etapa de Uoho", "Los años noventa", protegidas).ok
    assert rg.renombre_permitido("La etapa de Uoho", "La etapa de Uoho y Robe",
                                 protegidas).ok


def test_la_pagina_entera_no_puede_dejar_de_cubrir_lo_que_posiciona():
    antes = rg.pagina(CUERPO, "Extremoduro", "")
    despues = rg.pagina(CUERPO.replace("## Los primeros años", "## Los comienzos"),
                        "Extremoduro", "")
    v = rg.cobertura_conservada(antes, despues, PROTEGIDAS)
    assert not v.ok and v.perdidas == ["extremoduro primeros años"]


def test_solo_se_protege_lo_que_posiciona():
    qs = [{"query": "extremoduro lejos", "impressions": 50, "clicks": 0, "position": 35.0},
          {"query": "extremoduro cerca", "impressions": 50, "clicks": 0, "position": 12.0},
          {"query": "extremoduro clic", "impressions": 1, "clicks": 1, "position": 60.0},
          {"query": "extremoduro ruido", "impressions": 1, "clicks": 0, "position": 4.0}]
    # Un clic se protege siempre; sin clic, hace falta posición ≤ 20 e impresiones.
    assert [q["query"] for q in rg.consultas_protegidas(qs)] == [
        "extremoduro clic", "extremoduro cerca"]


def test_la_intro_reescrita_no_puede_soltar_datos():
    vieja = "Extremoduro fue el grupo de Robe, nacido en Plasencia en 1987."
    assert rg.datos_perdidos(vieja, "Extremoduro fue el grupo de Robe.") == ["Plasencia", "1987"]
    assert rg.datos_perdidos(vieja, "Nacido en Plasencia en 1987, Extremoduro fue el grupo "
                                    "de Robe y de sus integrantes.") == []


def test_enlace_entrante_en_la_primera_mencion_y_solo_una_vez():
    post = "## Intro\n\nLos integrantes de Extremoduro cambiaron. [Robe](/robe) siguió."
    nuevo, anchor = md.enlazar(post, "/personas", ["integrantes de Extremoduro"])
    assert "[integrantes de Extremoduro](/personas)" in nuevo and anchor == "integrantes de Extremoduro"
    # Criterio Moat: si ya enlaza a la página, no se añade otro.
    assert md.enlazar(nuevo, "/personas", ["integrantes de Extremoduro"]) is None
    # Ni se fuerza una frase que no está.
    assert md.enlazar("Nada que ver.", "/personas", ["integrantes de Extremoduro"]) is None


def test_el_enlace_no_cae_dentro_de_otro_enlace_ni_de_un_heading():
    post = "## Los integrantes de Extremoduro\n\n[integrantes de Extremoduro](/x) y luego integrantes de Extremoduro."
    nuevo, _ = md.enlazar(post, "/personas", ["integrantes de Extremoduro"])
    assert nuevo.endswith("y luego [integrantes de Extremoduro](/personas).")


def test_el_metatexto_de_la_primera_muestra_no_llega_a_la_pagina():
    """Literal de la primera muestra real (19-10-2026, /personas)."""
    sec = ("## Integrantes de Extremoduro\n\n"
           "Según esos periodos, Robe figura desde 1987 y Uoho desde 1996. Estos nombres "
           "y fechas responden a las búsquedas «integrantes de Extremoduro» e «integrantes "
           "Extremoduro»; no se añaden otros músicos sin periodos confirmados en el registro "
           "de miembros.\n\nExtremoduro anunció su disolución el 18 de diciembre de 2019.")
    limpio, quitadas = md.quitar_metatexto(sec)
    assert "búsquedas" not in limpio and "registro" not in limpio
    assert "Robe figura desde 1987 y Uoho desde 1996." in limpio
    assert "18 de diciembre de 2019" in limpio
    assert len(quitadas) == 1


def test_el_heading_no_se_toca_aunque_nombre_algo_parecido():
    limpio, quitadas = md.quitar_metatexto("## La búsqueda de un sonido\n\nTexto.")
    assert limpio.startswith("## La búsqueda de un sonido") and not quitadas


def test_no_se_lleva_por_delante_frases_normales():
    texto = "Grabaron el material en Madrid. Robe buscaba otro sonido."
    assert md.quitar_metatexto(texto) == (texto, [])


TITLE_PERSONAS = "Integrantes de Extremoduro y los colegas de Robe · Entre Interiores"


def test_el_title_que_ya_gana_la_busqueda_no_se_toca():
    """Literal de la primera muestra: proponía «Extremoduro: integrantes y miembros
    de la banda» para /personas, que está en pos. 7-11 con su title actual."""
    assert md.title_bloqueado(TITLE_PERSONAS, "Extremoduro: integrantes y miembros de la banda",
                              "integrantes de extremoduro")


def test_un_title_nuevo_no_puede_estrechar_la_pagina():
    viejo = "Extremoduro: historia y discos del grupo de Robe"
    assert "colegas" not in (md.title_bloqueado(viejo, "Extremoduro: género y estilo",
                                                "que genero es extremoduro") or "")
    assert md.title_bloqueado(viejo, "Extremoduro: género y estilo", "que genero es extremoduro")
    assert md.title_bloqueado(
        viejo, "Extremoduro: historia, discos y género del grupo de Robe",
        "que genero es extremoduro") is None


def test_la_marca_no_cuenta_como_contenido_del_title():
    assert md.title_bloqueado("Extremoduro · Entre Interiores", "Extremoduro: género musical",
                              "que genero es extremoduro") is None
