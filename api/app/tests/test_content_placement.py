"""¿Post nuevo o ampliar una página? Con las dos propuestas que lo destaparon.

Las filas de GSC son literales del volcado del 24-07 → 16-10-2026
(`data/gsc_page_queries.json`), recortadas a las consultas que importan.
"""
from __future__ import annotations

from app.services import content_placement as cp

PERIODO = "2026-07-24..2026-10-16"

GSC = {
    "/extremoduro": [
        {"query": "que genero es extremoduro", "impressions": 120, "clicks": 0, "position": 6.6},
        {"query": "extremoduro genero", "impressions": 61, "clicks": 0, "position": 6.8},
        {"query": "extremoduro que genero es", "impressions": 30, "clicks": 0, "position": 7.5},
        {"query": "componentes extremoduro", "impressions": 7, "clicks": 0, "position": 43.7},
        {"query": "componentes de extremoduro", "impressions": 5, "clicks": 0, "position": 48.0},
        {"query": "extremoduro componentes", "impressions": 5, "clicks": 0, "position": 39.0},
        {"query": "extremoduro integrantes", "impressions": 4, "clicks": 0, "position": 34.8},
        {"query": "integrantes de extremoduro", "impressions": 4, "clicks": 0, "position": 38.8},
        {"query": "integrantes extremoduro", "impressions": 2, "clicks": 0, "position": 48.5},
    ],
    "/discografia/extremoduro": [
        {"query": "componentes de extremoduro", "impressions": 5, "clicks": 0, "position": 84.0},
        {"query": "componentes extremoduro", "impressions": 3, "clicks": 0, "position": 95.7},
        {"query": "integrantes de extremoduro", "impressions": 3, "clicks": 0, "position": 89.7},
        {"query": "extremoduro componentes", "impressions": 2, "clicks": 0, "position": 96.5},
        {"query": "extremoduro genero", "impressions": 2, "clicks": 0, "position": 88.5},
        {"query": "extremoduro integrantes", "impressions": 2, "clicks": 0, "position": 92.0},
        {"query": "integrantes extremoduro", "impressions": 1, "clicks": 0, "position": 93.0},
    ],
    "/blog/la-evolucion-musical-de-extremoduro-un-viaje-inigualable": [
        {"query": "extremoduro que genero es", "impressions": 6, "clicks": 0, "position": 10.2},
        {"query": "extremoduro genero", "impressions": 1, "clicks": 0, "position": 64.0},
    ],
    "/personas": [
        {"query": "miembros de extremoduro", "impressions": 329, "clicks": 2, "position": 9.0},
        {"query": "extremoduro integrantes", "impressions": 297, "clicks": 0, "position": 7.8},
        {"query": "componentes de extremoduro", "impressions": 157, "clicks": 3, "position": 7.7},
        {"query": "integrantes extremoduro", "impressions": 143, "clicks": 0, "position": 8.0},
        {"query": "integrantes de extremoduro", "impressions": 140, "clicks": 0, "position": 7.5},
        {"query": "componentes extremoduro", "impressions": 75, "clicks": 0, "position": 9.9},
        {"query": "extremoduro componentes", "impressions": 74, "clicks": 0, "position": 11.1},
    ],
}

KW_484 = ["integrantes de extremoduro", "componentes de extremoduro", "integrantes extremoduro"]
KW_485 = ["que genero es extremoduro", "extremoduro necesito droga y amor",
          "extremoduro cancion de amor"]


def _candidatos(keywords, *, personas_editable=True):
    """Como `analyze`, pero sin BD: el tipo de cada ruta se da a mano."""
    out = []
    for path, hits in cp.gsc_matches(GSC, keywords).items():
        if path.startswith("/blog/"):
            c = cp.Candidate(path=path, kind="post", label=path, target="post:7")
        elif path == "/discografia/extremoduro" or (path == "/personas"
                                                    and not personas_editable):
            c = cp.Candidate(path=path, kind="code", label=path)
        else:
            c = cp.Candidate(path=path, kind="ficha", label=path, target=f"ficha:{path}")
        c.gsc_impressions, c.gsc_clicks, c.gsc_position = cp._agregar(hits)
        out.append(c)
    return out


def test_484_integrantes_lo_gana_personas_no_la_ficha_del_grupo():
    p = cp.decide(_candidatos(KW_484), period=PERIODO)
    assert p.decision == "ampliar"
    assert p.recommended == "ficha:/personas"
    assert p.confidence == "alta"
    assert p.candidates[0].path == "/personas"
    # 886 = las seis variantes de integrantes/componentes; «miembros» no es
    # keyword de la propuesta y no cuenta.
    assert p.candidates[0].gsc_impressions == 886
    assert "/personas" in p.reasons[0] and "886 impresiones" in p.reasons[0]


def test_485_genero_amplia_la_ficha_y_marca_la_canibalizacion():
    p = cp.decide(_candidatos(KW_485), period=PERIODO)
    assert p.decision == "ampliar"
    assert p.recommended == "ficha:/extremoduro"
    assert "/blog/la-evolucion-musical-de-extremoduro-un-viaje-inigualable" in p.competing
    assert any("Ya compiten 2 páginas" in r for r in p.reasons)


def test_la_misma_busqueda_en_otro_orden_es_la_misma():
    assert cp._firma("extremoduro integrantes") == cp._firma("integrantes de extremoduro")
    assert cp._firma("extremoduro integrantes 1990") != cp._firma("integrantes extremoduro")


def test_una_pagina_de_codigo_que_posiciona_frena_el_post_aunque_no_se_pueda_fundir():
    """Antes de la migración, /personas vivía en código: el motor no la puede
    escribir, pero un post nuevo le seguiría quitando la consulta."""
    p = cp.decide(_candidatos(KW_484, personas_editable=False), period=PERIODO)
    assert p.decision == "ampliar"
    assert p.recommended is None
    assert p.candidates[0].path == "/personas" and not p.candidates[0].mergeable
    assert cp.headline(p.to_dict()).startswith("Ya lo cubre /personas")
    # El selector no ofrece fundir con algo que no se puede escribir.
    assert all(o["value"] != "code" for o in cp.selector_options(p.to_dict()))


def test_sin_dueno_en_gsc_el_parecido_nunca_da_confianza_alta():
    c = cp.Candidate(path="/extremoduro", kind="ficha", label="x", target="ficha:1",
                     similarity=0.71)
    p = cp.decide([c], semantic_checked=True)
    assert p.decision == "ampliar" and p.confidence == "baja"


def test_sin_ninguna_senal_es_contenido_nuevo_con_confianza_baja():
    p = cp.decide([])
    assert p.decision == "nuevo" and p.confidence == "baja"
    opts = cp.selector_options(p.to_dict())
    assert [o["value"] for o in opts] == ["new", "skip"]
    assert opts[0]["recommended"] and not opts[1]["recommended"]


def test_el_selector_marca_el_recomendado_y_siempre_ofrece_contenido_nuevo():
    opts = cp.selector_options(cp.decide(_candidatos(KW_485), period=PERIODO).to_dict())
    assert opts[0] == {"value": "ficha:/extremoduro", "label": "Ampliar /extremoduro",
                       "path": "/extremoduro", "recommended": True}
    assert [o["value"] for o in opts[-2:]] == ["new", "skip"]
    assert not opts[-1]["recommended"] and not opts[-2]["recommended"]


def test_las_cifras_salen_con_coma_decimal():
    p = cp.decide(_candidatos(KW_484), period=PERIODO)
    assert "posición media 8,2" in p.reasons[0]
    assert "2026-07-24 → 2026-10-16" in p.reasons[0]


# --------------------------------------------------------------------------- #
# Cada keyword a su página (borrador #40: «necesito droga y amor» acabó en
# /extremoduro, cuando es de la ficha de la canción)
# --------------------------------------------------------------------------- #
CANCION = "/extremoduro/somos-unos-animales/necesito-droga-y-amor-los-camellos-no-me-fian"


def _titulo(kw):
    if "necesito droga y amor" in kw:
        return CANCION, "Necesito droga y amor"
    return None


def test_485_cada_keyword_a_su_pagina():
    rutas = dict(cp.repartir(
        KW_485, por_gsc=lambda kw: cp.dueno_gsc(GSC, kw), por_titulo=_titulo,
        por_semantica=lambda kw: None))
    assert rutas["que genero es extremoduro"].path == "/extremoduro"
    assert rutas["que genero es extremoduro"].via == "gsc"
    assert rutas["extremoduro necesito droga y amor"].path == CANCION
    assert rutas["extremoduro necesito droga y amor"].via == "titulo"
    # «canción de amor» no es de ninguna página: va a su propio grupo.
    assert rutas["extremoduro cancion de amor"].path is None


def test_el_dueno_en_gsc_exige_estar_en_el_top_20():
    # /discografia/extremoduro recibe impresiones de «componentes de extremoduro»,
    # pero en la pos. 84: no es de ella. Es de /personas.
    assert cp.dueno_gsc(GSC, "componentes de extremoduro")[0] == "/personas"
    assert cp.dueno_gsc({"/x": [{"query": "componentes de extremoduro",
                                 "impressions": 50, "position": 84.0}]},
                        "componentes de extremoduro") is None


def test_ya_cubierto_es_cuerpo_meta_y_top_10():
    body = "## El género\n\nExtremoduro hacía rock transgresivo: ese es su género."
    gsc = [{"query": "que genero es extremoduro", "impressions": 120, "position": 6.6}]
    assert cp.ya_cubierto(body, "Extremoduro: género y discos", "", ["que genero es extremoduro"],
                          gsc)
    # Sin la promesa en el title/description, falta meta, no está «cubierto».
    assert not cp.ya_cubierto(body, "Extremoduro: discos", "", ["que genero es extremoduro"],
                              gsc)
    # Fuera del top 10, tampoco.
    assert not cp.ya_cubierto(body, "Extremoduro: género", "", ["que genero es extremoduro"],
                              [{**gsc[0], "position": 14.0}])


def test_las_keywords_desactivadas_no_cuentan():
    class _P:
        target_keyword = "extremoduro cancion de amor"
        keywords = [{"keyword": "extremoduro cancion de amor", "excluded": True},
                    {"keyword": "extremoduro necesito droga y amor"}]

    assert cp.proposal_keywords(_P()) == ["extremoduro necesito droga y amor"]
