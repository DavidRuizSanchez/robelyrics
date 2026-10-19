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


# --------------------------------------------------------------------------- #
# Fusión v2 (19-10-2026): lo cubierto se mejora en su sitio, el juez lee el
# contexto y un rechazo no se presenta.
# --------------------------------------------------------------------------- #
FICHA_LARGA = ("Extremoduro fue el grupo de Robe.\n\n"
               "## Rock transgresivo: el nombre de un género\n\n"
               "Extremoduro definió su género como rock transgresivo. " * 1
               + "\n\n"
               + "\n\n".join(f"## Sección {i}\n\n" + ("Texto largo de relleno real. " * 60)
                             for i in range(12))
               + "\n\n## El final\n\nLa banda se disolvió en 2019.\n")


def test_la_cobertura_dice_que_seccion_ya_responde_cada_consulta():
    mapa = md.cobertura_por_seccion(FICHA_LARGA, ["que genero es extremoduro",
                                                  "extremoduro cancion de amor"])
    assert mapa["que genero es extremoduro"] == "Rock transgresivo: el nombre de un género"
    assert mapa["extremoduro cancion de amor"] is None


def test_enriquecer_anade_al_final_de_su_seccion_sin_tocar_lo_demas():
    ops = md.Operaciones(enriquecer=[{"heading": "El final",
                                      "texto": "Robe murió en diciembre de 2025."}])
    despues = md.aplicar(CUERPO, ops)
    assert "La banda se disolvió en 2019.\n\nRobe murió en diciembre de 2025." in despues
    assert md.secciones_conservadas(CUERPO, despues, ops) == []


def test_el_juez_lee_el_contexto_y_no_un_recorte():
    """Sobre /extremoduro (23.700 caracteres) el juez leía `body[:9000]` y ponía un 18
    al «antes» porque «el artículo queda truncado»."""
    assert len(FICHA_LARGA) > 9000
    ext = md.extracto_local(FICHA_LARGA, {"El final"})
    assert ext.startswith("ESQUEMA DE LA PÁGINA:") and "El final" in ext
    assert "La banda se disolvió en 2019." in ext      # la cola que el recorte perdía
    assert "Sección 11" in ext                          # su vecina
    assert "Sección 3\n" not in ext                     # lo lejano no
    assert len(ext) < 9000


class _V:
    def __init__(self, verdict, score):
        self.verdict, self.score, self.reasons = verdict, score, ["repite lo que ya dice"]


def _motor_merge(monkeypatch, *, veredicto, despues=40):
    """Cablea `merge_page` sin red: el juez devuelve lo que se le pida."""
    from types import SimpleNamespace

    from scripts.seo import augment_deep, generate_deep

    destino = md.Destino("ficha", SimpleNamespace(target_keyword=None), "/extremoduro",
                         "Extremoduro", "artist", object(), CUERPO, "Extremoduro", "", "x")
    monkeypatch.setattr(md, "cargar_destino", lambda db, opp: destino)
    monkeypatch.setattr(md, "reunir_material", lambda db, c, d, q: md.Material(
        escritor="DATOS PROPIOS", verificable="Extremoduro 1987 Plasencia", hard="", pasajes=0))
    monkeypatch.setattr(md, "planificar", lambda *a, **kw: {
        "insert": [{"after": "El final", "heading": "La gira de despedida",
                    "covers": "la gira"}]})
    monkeypatch.setattr("app.services.seo_opportunities.nombre_alias_index", lambda db: {})
    monkeypatch.setattr("app.services.source_guard.nombres_de_fuentes", lambda db=None: [])
    monkeypatch.setattr("app.services.content_placement.load_gsc_pages", lambda: ({}, None))
    llamadas = {"escritas": 0}

    def _escribe(*a, **kw):
        llamadas["escritas"] += 1
        return "## La gira de despedida\n\nExtremoduro anunció una gira en 2019 en Plasencia."

    monkeypatch.setattr(generate_deep, "_write_section", _escribe)
    monkeypatch.setattr(generate_deep, "_verify_section", lambda c, t, m: t)
    monkeypatch.setattr(augment_deep, "confiesa_no_saber", lambda t: None)
    monkeypatch.setattr("app.services.editorial_review.review",
                        lambda body, **kw: _V(veredicto, despues) if kw.get("spotlight")
                        else _V("pass", 60))
    opp = SimpleNamespace(queries=[{"query": "extremoduro gira despedida"}], gap_hint="")
    return opp, llamadas


def test_un_rechazo_tras_dos_reescrituras_no_se_presenta(monkeypatch):
    opp, llamadas = _motor_merge(monkeypatch, veredicto="reject")
    res = md.merge_page(object(), object(), opp)
    assert res["noop"] is True
    assert llamadas["escritas"] == md.MAX_VUELTAS + 1
    assert any("editor jefe no la ve mejor" in d for d in res["notas"]["descartado"])


def test_si_el_juez_la_ve_mejor_sale_borrador_a_la_primera(monkeypatch):
    opp, llamadas = _motor_merge(monkeypatch, veredicto="pass", despues=68)
    monkeypatch.setattr(md, "propose_meta", lambda *a, **kw: {}, raising=False)
    monkeypatch.setattr("app.services.seo_opportunities.propose_meta", lambda *a, **kw: {})
    monkeypatch.setattr(md, "coser", lambda *a, **kw: {})
    monkeypatch.setattr("app.services.entity_resolver.build_corpus_index", lambda db: [])
    monkeypatch.setattr("app.services.entity_resolver.load_link_stats", lambda: {})
    monkeypatch.setattr("app.services.url_resolver.guard_internal_links",
                        lambda db, t: type("G", (), {"body_md": t, "changed": False})())
    monkeypatch.setattr("app.services.lyric_guard.check_lyrics",
                        lambda db, t: type("R", (), {"blocking": []})())
    res = md.merge_page(object(), object(), opp)
    assert res["noop"] is False, res.get("motivo")
    assert llamadas["escritas"] == 1
    assert "## La gira de despedida" in res["after"]
    assert res["notas"]["juez"][-1]["despues"] == 68


def test_el_juez_ve_lo_nuevo_una_sola_vez(monkeypatch):
    """En la prueba del 19-10-2026 lo añadido iba dentro del contexto Y por
    `spotlight`, y el juez respondía «repite literalmente el párrafo»."""
    vistos = []

    def _review(body, **kw):
        vistos.append((body, kw.get("spotlight")))
        return _V("pass", 70 if kw.get("spotlight") else 60)

    monkeypatch.setattr("app.services.editorial_review.review", _review)
    j = md.juzgar("CONTEXTO PUBLICADO", "LO NUEVO", kind="artist", subject="Extremoduro",
                  consultas=["x"], material="")
    assert [b for b, _ in vistos] == ["CONTEXTO PUBLICADO", "CONTEXTO PUBLICADO"]
    assert [sp for _, sp in vistos] == [None, "LO NUEVO"]
    assert j.ok


def test_si_sube_la_nota_vale_aunque_la_pagina_base_siga_rechazada(monkeypatch):
    monkeypatch.setattr("app.services.editorial_review.review",
                        lambda body, **kw: _V("reject", 30 if kw.get("spotlight") else 18))
    assert md.juzgar("c", "n", kind="artist", subject="E", consultas=[], material="").ok
    monkeypatch.setattr("app.services.editorial_review.review",
                        lambda body, **kw: _V("reject", 18))
    assert not md.juzgar("c", "n", kind="artist", subject="E", consultas=[], material="").ok
