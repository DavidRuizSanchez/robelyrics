"""Enlazado interno: rutas normalizadas y punto fijo (11-11-2026).

`/personas/alen-ayerdi` llegó a enlazar 6 veces a El Dromedario Records con el
mismo anchor. No lo escribió el modelo: el índice del corpus ponía los sellos en
`/grupos/`, el guard los reescribía a `/sellos/` relativo y el autolinker
comparaba las URLs en crudo, así que no veía el enlace que ya había y enlazaba
la siguiente mención. Un enlace más por pasada del cron.

El fixture es el cuerpo publicado en prod el 11-11-2026, con sus 6 enlaces.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.db.models import Band
from app.services.entity_resolver import autolink_corpus, build_corpus_index
from app.services.link_policy import ENLACE as _ENLACE
from app.services.link_policy import norm_path
from app.services.url_resolver import _reenlazar
from app.tests.test_person_visibility import db  # noqa: F401 — fixture SQLite
from scripts.seo.relink_existing import _clean

BASE = "https://entreinteriores.com"
ALEN = (Path(__file__).parent / "fixtures" / "alen_ayerdi_body.md").read_text()
DROMEDARIO = "/sellos/el-dromedario-records"

def _destinos(md: str) -> list[str]:
    return [norm_path(u) or u for _, u in _ENLACE.findall(md)]


def _ent(name: str, path: str, type_: str) -> dict:
    return {"name": name, "norm": name.lower(), "url": BASE + path, "type": type_}


INDICE_ALEN = [
    _ent("Marea", "/grupos/marea", "band"),
    _ent("Extremoduro", "/extremoduro", "artist"),
    _ent("El Dromedario Records", DROMEDARIO, "band"),
    _ent("Lo que aletea en nuestras cabezas",
         "/robe/lo-que-aletea-en-nuestras-cabezas", "album"),
    _ent("Mayéutica", "/robe/mayeutica", "album"),
    _ent("Ciclonautas", "/grupos/ciclonautas", "band"),
    _ent("Pamplona", "/lugares/pamplona", "place"),
]


# --------------------------------------------------------------------------- #
# norm_path
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("url,esperado", [
    ("https://entreinteriores.com/sellos/x", "/sellos/x"),
    ("https://www.entreinteriores.com/sellos/x/", "/sellos/x"),
    ("/sellos/x", "/sellos/x"),
    ("/sellos/x/", "/sellos/x"),
    ("/sellos/x#historia", "/sellos/x"),
    ("/sellos/x?utm=1", "/sellos/x"),
    ("https://entreinteriores.com", "/"),
    ("/", "/"),
])
def test_norm_path_internas(url, esperado):
    assert norm_path(url) == esperado


@pytest.mark.parametrize("url", [
    "https://es.wikipedia.org/wiki/Extremoduro",
    "https://entreinteriores.com.evil.example/sellos/x",
    "mailto:hola@example.com",
    "#notas",
    "",
    None,
    "relativa/sin/barra",
])
def test_norm_path_externas_o_no_navegables(url):
    assert norm_path(url) is None


# --------------------------------------------------------------------------- #
# Relativa contra absoluta: la causa raíz
# --------------------------------------------------------------------------- #
def test_un_enlace_relativo_cuenta_como_el_absoluto_del_indice():
    md = "Fundó [El Dromedario Records](/sellos/el-dromedario-records). Luego El Dromedario Records creció."
    indice = [_ent("El Dromedario Records", DROMEDARIO, "band")]
    assert autolink_corpus(md, indice, max_links=4) == md


def test_barra_final_y_fragmento_no_cuentan_como_otro_destino():
    md = "Ver [Extremoduro](/extremoduro/#historia). Extremoduro grabó Agila."
    indice = [_ent("Extremoduro", "/extremoduro", "artist")]
    assert autolink_corpus(md, indice, max_links=4) == md


def test_el_relativo_consume_tope():
    """Un enlace ya presente al corpus, relativo, gasta presupuesto."""
    md = "[Marea](/grupos/marea) y Extremoduro."
    indice = [_ent("Marea", "/grupos/marea", "band"),
              _ent("Extremoduro", "/extremoduro", "artist")]
    assert autolink_corpus(md, indice, max_links=1) == md


# --------------------------------------------------------------------------- #
# Índice: los sellos van a /sellos/
# --------------------------------------------------------------------------- #
def test_los_sellos_se_indexan_en_sellos_y_los_grupos_en_grupos(db):  # noqa: F811
    db.add_all([
        Band(slug="el-dromedario-records", name="El Dromedario Records", kind="label"),
        Band(slug="marea", name="Marea", kind="band"),
    ])
    db.flush()
    urls = {e["name"]: e["url"] for e in build_corpus_index(db)}
    assert urls["El Dromedario Records"] == BASE + DROMEDARIO
    assert urls["Marea"] == BASE + "/grupos/marea"


# --------------------------------------------------------------------------- #
# Punto fijo: el ciclo real del cron no acumula
# --------------------------------------------------------------------------- #
def _guard_relativiza(md: str) -> str:
    """Peor caso del guard / `audit_urls --fix`: reescribe a relativa toda ruta
    interna absoluta (lo que hace `_reenlazar` con las que redirigen)."""
    for url in {u for _, u in _ENLACE.findall(md) if u.startswith(BASE)}:
        md = _reenlazar(md, norm_path(url), norm_path(url))
    return md


def _semana(md: str, n: int) -> str:
    # `link_stats` cambia cada semana: el resultado no puede depender de ello.
    stats = {norm_path(e["url"]): (n * 7 + i) % 5 for i, e in enumerate(INDICE_ALEN)}
    md = _clean(md, INDICE_ALEN, stats, exclude_slug="alen-ayerdi")
    return _guard_relativiza(md)


def test_alen_ayerdi_no_suma_un_enlace_por_pasada():
    antes = _destinos(ALEN).count(DROMEDARIO)
    assert antes == 6  # el estado real de prod el 11-11-2026
    md = ALEN
    for n in range(6):
        md = _semana(md, n)
    # Nunca crece. Quitar los 5 sobrantes es la limpieza (otro PR), no el cron.
    assert _destinos(md).count(DROMEDARIO) == antes
    # Ya tiene sus 4 destinos del corpus: el cron no tiene nada que añadir.
    assert md == _guard_relativiza(ALEN)


def test_ciclo_completo_es_punto_fijo_desde_la_segunda_pasada():
    sin_enlaces = _ENLACE.sub(r"\1", ALEN)
    primera = _semana(sin_enlaces, 0)
    assert _destinos(primera), "la primera pasada tiene que enlazar algo"
    md = primera
    for n in range(1, 6):
        md = _semana(md, n)
        assert md == primera, f"la pasada {n + 1} cambió el cuerpo"


def test_primera_pasada_enlaza_cada_destino_una_sola_vez():
    sin_enlaces = _ENLACE.sub(r"\1", ALEN)
    destinos = _destinos(_semana(sin_enlaces, 0))
    assert len(destinos) == len(set(destinos))
    assert len(destinos) <= 4


def test_relink_no_pierde_ningun_enlace_del_cuerpo_real():
    md = _semana(ALEN, 0)
    assert _ENLACE.sub(r"\1", md) == _ENLACE.sub(r"\1", ALEN)  # mismo texto
    assert sorted(_destinos(md)) == sorted(_destinos(_guard_relativiza(ALEN)))


# --------------------------------------------------------------------------- #
# Reglas de David del 11-11-2026 (link_policy)
# --------------------------------------------------------------------------- #
from types import SimpleNamespace  # noqa: E402

from app.services.link_policy import (  # noqa: E402
    MAX_BODY_LINKS,
    ContextoEnlazado,
    Relaciones,
    cargar_relaciones,
    presupuesto,
    rutas_del_cuerpo,
)

INDICE_RICO = [
    _ent("Agila", "/extremoduro/agila", "album"),
    _ent("Pedrá", "/extremoduro/pedra", "album"),
    _ent("Deltoya", "/extremoduro/deltoya", "album"),
    _ent("La ley innata", "/extremoduro/la-ley-innata", "album"),
    _ent("Somos unos animales", "/extremoduro/somos-unos-animales", "album"),
    _ent("Lucha", "/temas/lucha", "theme"),
    _ent("Plasencia", "/lugares/plasencia", "place"),
    _ent("discografía de Extremoduro", "/discografia/extremoduro", "hub"),
    _ent("discos de Extremoduro", "/discografia/extremoduro", "hub"),
    _ent("discografía de Robe", "/discografia/robe", "hub"),
]
TEXTO_RICO = ("Agila, Pedrá, Deltoya, La ley innata y Somos unos animales son discos. "
              "Hubo mucha lucha en Plasencia.")


def test_tope_de_3_en_el_cuerpo():
    out = autolink_corpus(TEXTO_RICO, INDICE_RICO)
    assert len(set(rutas_del_cuerpo(out))) == MAX_BODY_LINKS


def test_un_max_links_mayor_se_recorta_al_tope():
    out = autolink_corpus(TEXTO_RICO, INDICE_RICO, max_links=10)
    assert len(set(rutas_del_cuerpo(out))) == MAX_BODY_LINKS


def test_cuentan_los_enlaces_que_no_son_del_indice():
    md = "[A](/libros/a), [B](/estudios/b) y [C](/blog/c). Agila y Pedrá."
    assert autolink_corpus(md, INDICE_RICO) == md


def test_no_enlaza_lo_que_ya_enlaza_la_plantilla_ni_lo_cuenta():
    ctx = ContextoEnlazado(origen="/extremoduro/agila/so-payaso",
                           plantilla=frozenset({"/extremoduro/agila"}))
    md = "[Agila](/extremoduro/agila) es de 1996. Pedrá, Deltoya y La ley innata vinieron luego."
    out = autolink_corpus(md, INDICE_RICO, contexto=ctx)
    propios = set(rutas_del_cuerpo(out)) - ctx.plantilla
    assert len(propios) == MAX_BODY_LINKS  # el de la plantilla no gastó presupuesto
    assert presupuesto(out, ctx.plantilla) == 0


def test_sin_contexto_no_enlaza_temas_pero_si_lugares():
    out = autolink_corpus("Hubo mucha lucha en Plasencia.", INDICE_RICO)
    assert rutas_del_cuerpo(out) == ["/lugares/plasencia"]


def test_taxonomia_solo_con_relacion_en_el_grafo():
    rel = Relaciones({"/extremoduro/agila/so-payaso": {"/temas/lucha"},
                      "/temas/lucha": {"/extremoduro/agila/so-payaso"},
                      "/lugares/plasencia": {"/extremoduro/otra"}})
    ctx = ContextoEnlazado(origen="/extremoduro/agila/so-payaso", relaciones=rel)
    out = autolink_corpus("Hubo mucha lucha en Pedrá.", INDICE_RICO, contexto=ctx)
    assert sorted(rutas_del_cuerpo(out)) == ["/extremoduro/pedra", "/temas/lucha"]
    otro = ContextoEnlazado(origen="/extremoduro/agila/sucede", relaciones=rel)
    assert rutas_del_cuerpo(autolink_corpus("Hubo mucha lucha.", INDICE_RICO, contexto=otro)) == []


def test_las_aristas_mentions_no_relacionan():
    """Si contaran, la propia mención justificaría el enlace (circular)."""
    edges = [SimpleNamespace(src_type="song", src_id=1, dst_type="theme", dst_id=2,
                             edge_type="mentions"),
             SimpleNamespace(src_type="song", src_id=1, dst_type="place", dst_id=3,
                             edge_type="song_place")]
    db = SimpleNamespace(query=lambda _m: SimpleNamespace(all=lambda: edges))
    rutas = {("song", 1): "/x/y/z", ("theme", 2): "/temas/lucha", ("place", 3): "/lugares/plasencia"}
    rel = cargar_relaciones(db, rutas)
    assert not rel.relacionados("/x/y/z", "/temas/lucha")
    assert rel.relacionados("/x/y/z", "/lugares/plasencia")


def test_hub_solo_el_del_artista_de_la_pagina():
    md = "Repasa la discografía de Robe y la discografía de Extremoduro."
    ctx = ContextoEnlazado(origen="/extremoduro/agila/so-payaso")
    assert rutas_del_cuerpo(autolink_corpus(md, INDICE_RICO, contexto=ctx)) == [
        "/discografia/extremoduro"]


def test_como_mucho_un_hub_por_pagina():
    md = "Repasa la discografía de Robe y la discografía de Extremoduro."
    ctx = ContextoEnlazado(origen="/blog/un-post")  # sin artista: valdrían los dos
    out = autolink_corpus(md, INDICE_RICO, contexto=ctx)
    assert len([p for p in rutas_del_cuerpo(out) if p.startswith("/discografia/")]) == 1


def test_el_hub_no_recibe_el_impulso_de_pagina_debil():
    md = "Los discos de Extremoduro empiezan con Pedrá."
    ctx = ContextoEnlazado(origen="/extremoduro/agila/so-payaso")
    out = autolink_corpus(md, INDICE_RICO, contexto=ctx, max_links=1,
                          link_stats={"/discografia/extremoduro": 0, "/extremoduro/pedra": 500})
    assert rutas_del_cuerpo(out) == ["/extremoduro/pedra"]


def test_anchor_ampliado_si_el_corto_esta_gastado():
    md = "Así sonaba el disco *Agila* en 1996."
    gastado = {"/extremoduro/agila": {"agila": 40}}
    out = autolink_corpus(md, INDICE_RICO, anchor_stats=gastado)
    assert "[el disco *Agila*](https://entreinteriores.com/extremoduro/agila)" in out
    assert _ENLACE.sub(r"\1", out) == md  # no se reescribe ninguna palabra


def test_sin_estadisticas_usa_el_nombre():
    md = "Así sonaba el disco Agila en 1996."
    out = autolink_corpus(md, INDICE_RICO)
    assert "el disco [Agila](" in out or "[el disco Agila](" in out
    assert _ENLACE.sub(r"\1", out) == md


def test_el_tope_es_de_la_pagina_entera():
    """merge_deep enlaza por secciones: lo ya enlazado en la página cuenta."""
    out = autolink_corpus("Agila y Pedrá.", INDICE_RICO,
                          ya_en_pagina=["/a", "/b", "/extremoduro/deltoya"])
    assert rutas_del_cuerpo(out) == []


@pytest.fixture()
def bd():
    from sqlalchemy import ARRAY, JSON, MetaData, Text, create_engine
    from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
    from sqlalchemy.orm import Session

    from app.db.models import (
        Album,
        AlbumTrack,
        Artist,
        BandMembership,
        Concept,
        EntityEdge,
        Person,
        Place,
        SeoContent,
        Song,
        SongConcept,
        SongCredit,
        SongPlace,
        SongTheme,
        Theme,
    )
    from app.tests.test_admin_summary import _con_dependencias

    md = MetaData()
    modelos = (Artist, Album, Song, AlbumTrack, Person, Band, BandMembership, SongCredit,
               Theme, Place, Concept, SongTheme, SongPlace, SongConcept, EntityEdge, SeoContent)
    for tabla in _con_dependencias([m.__table__ for m in modelos]):
        t = tabla.to_metadata(md)
        for col in t.columns:
            if isinstance(col.type, (JSONB, ARRAY)):
                col.type = JSON()
            elif isinstance(col.type, TSVECTOR):
                col.type = Text()
            sd = col.server_default
            if sd is not None and "::" in str(getattr(sd, "arg", "")):
                col.server_default = None
        t.indexes.clear()
    engine = create_engine("sqlite://")
    md.create_all(engine)
    with Session(engine) as s:
        yield s


def _catalogo(bd):
    from app.db.models import Album, Artist, EntityEdge, Song, SongTheme, Theme

    art = Artist(slug="extremoduro", name="Extremoduro")
    bd.add(art)
    bd.flush()
    discos = [Album(slug=s, title=s.title(), year=y, artist_id=art.id)
              for s, y in (("rock-transgresivo", 1989), ("somos-unos-animales", 1991),
                           ("deltoya", 1992), ("agila", 1996))]
    bd.add_all(discos)
    bd.flush()
    agila = discos[-1]
    so, sucede = (Song(slug="so-payaso", title="So Payaso", album_id=agila.id, track_number=4),
                  Song(slug="sucede", title="Sucede", album_id=agila.id, track_number=3))
    lucha, amor = Theme(slug="lucha", name="Lucha"), Theme(slug="amor", name="Amor")
    bd.add_all([so, sucede, lucha, amor])
    bd.flush()
    bd.add(SongTheme(song_id=so.id, theme_id=lucha.id))
    bd.add(EntityEdge(src_type="song", src_id=sucede.id, src_slug="sucede", edge_type="song_theme",
                      dst_type="theme", dst_id=amor.id, dst_slug="amor", weight=1.0))
    bd.add(EntityEdge(src_type="song", src_id=so.id, src_slug="so-payaso", edge_type="mentions",
                      dst_type="theme", dst_id=amor.id, dst_slug="amor", weight=0.5))
    bd.flush()
    return SimpleNamespace(art=art, agila=agila, so=so, sucede=sucede)


def test_plantilla_de_una_cancion(bd):
    from app.services.link_policy import plantilla_de, rutas_de_nodos

    c = _catalogo(bd)
    p = plantilla_de(bd, "song", c.so.id, rutas_de_nodos(bd))
    assert p == {"/extremoduro/agila", "/extremoduro/agila/sucede", "/temas/lucha"}


def test_plantilla_de_un_disco_incluye_mas_discos(bd):
    from app.services.link_policy import plantilla_de, rutas_de_nodos

    c = _catalogo(bd)
    p = plantilla_de(bd, "album", c.agila.id, rutas_de_nodos(bd))
    assert {"/extremoduro", "/extremoduro/agila/so-payaso", "/extremoduro/deltoya",
            "/extremoduro/rock-transgresivo", "/discografia/extremoduro"} <= p
    assert "/extremoduro/agila" not in p


def test_contexto_de_una_cancion_relaciona_por_aristas_reales(bd):
    from app.services.link_policy import contexto_de

    c = _catalogo(bd)
    ctx = contexto_de(bd, "song", c.sucede.id)
    assert ctx.origen == "/extremoduro/agila/sucede"
    assert ctx.admite("/temas/amor")             # arista song_theme real
    assert not ctx.admite("/temas/lucha")        # no es suyo
    assert not contexto_de(bd, "song", c.so.id).admite("/temas/amor")  # solo `mentions`


# --------------------------------------------------------------------------- #
# Limpieza de lo publicado (recortar)
# --------------------------------------------------------------------------- #
from app.services.link_policy import recortar, solo_cambian_enlaces  # noqa: E402

TIPOS_ALEN = {"/grupos/marea": "band", "/extremoduro": "artist", DROMEDARIO: "band",
              "/robe/lo-que-aletea-en-nuestras-cabezas": "album"}


def test_recorte_de_alen_ayerdi():
    r = recortar(ALEN, ContextoEnlazado(origen="/personas/alen-ayerdi"), tipo_de=TIPOS_ALEN)
    assert solo_cambian_enlaces(ALEN, r.md)
    assert _destinos(r.md).count(DROMEDARIO) == 1
    assert [q[2] for q in r.quitados].count("repetido") == 5
    assert len(set(_destinos(r.md))) == MAX_BODY_LINKS
    # Sale el de menos menciones: «Lo que aletea…» (2) frente a Marea (6),
    # Extremoduro (4) y Dromedario (7).
    assert [q[1] for q in r.quitados if q[2] == "tope"] == [
        "/robe/lo-que-aletea-en-nuestras-cabezas"]


def test_recorte_se_queda_el_primer_enlace_de_cada_destino():
    md = "Primero [Agila](/extremoduro/agila), luego [el disco Agila](/extremoduro/agila)."
    r = recortar(md, ContextoEnlazado())
    assert r.md == "Primero [Agila](/extremoduro/agila), luego el disco Agila."


def test_recorte_quita_la_taxonomia_sin_relacion_y_no_toca_lo_de_la_plantilla():
    """Lo que repite la plantilla se pinta como texto al servir: no se borra de
    la BD ni gasta tope (asesor, 11-11-2026)."""
    md = ("En [Agila](/extremoduro/agila) hay [lucha](/temas/lucha), [Pedrá](/extremoduro/pedra), "
          "[Deltoya](/extremoduro/deltoya) y [Somos](/extremoduro/somos-unos-animales).")
    ctx = ContextoEnlazado(origen="/extremoduro/agila/so-payaso",
                           plantilla=frozenset({"/extremoduro/agila"}))
    r = recortar(md, ctx)
    assert "[Agila](/extremoduro/agila)" in r.md and "[lucha]" not in r.md
    assert [q[2] for q in r.quitados] == ["sin_relacion"]


def test_el_tope_protege_al_destino_poco_enlazado():
    md = "[A](/a) [B](/b) [C](/c) [D](/sellos/avispa)."
    stats = {"/a": 300, "/b": 300, "/c": 300, "/sellos/avispa": 0}
    r = recortar(md, ContextoEnlazado(), link_stats=stats)
    assert "/sellos/avispa" in rutas_del_cuerpo(r.md)
    assert len(rutas_del_cuerpo(r.md)) == MAX_BODY_LINKS


def test_las_migas_no_se_usan_para_rellenar():
    """Una canción ya enlaza su artista y su disco en las migas."""
    indice = [_ent("Extremoduro", "/extremoduro", "artist")] + INDICE_RICO
    ctx = ContextoEnlazado(origen="/extremoduro/agila/so-payaso")
    assert ctx.migas == {"/extremoduro", "/extremoduro/agila"}
    out = autolink_corpus("Extremoduro grabó Agila y luego Pedrá.", indice, contexto=ctx)
    assert rutas_del_cuerpo(out) == ["/extremoduro/pedra"]


def test_un_enlace_del_cuerpo_a_las_migas_si_cuenta_para_el_tope():
    ctx = ContextoEnlazado(origen="/extremoduro/agila/so-payaso")
    md = "[Extremoduro](/extremoduro), [Pedrá](/extremoduro/pedra), [Deltoya](/extremoduro/deltoya)."
    assert presupuesto(md, ctx.plantilla) == 0


def test_recorte_no_toca_externos_ni_imagenes():
    md = ("![Portada](/album-covers/agila.jpg) Según [Genius](https://genius.com/x), "
          "[A](/a) [B](/b) [C](/c) [D](/d).")
    r = recortar(md, ContextoEnlazado())
    assert solo_cambian_enlaces(md, r.md)
    assert "![Portada](/album-covers/agila.jpg)" in r.md and "[Genius](https://genius.com/x)" in r.md
    assert len(rutas_del_cuerpo(r.md)) == MAX_BODY_LINKS


def test_recorte_es_idempotente():
    ctx = ContextoEnlazado(origen="/personas/alen-ayerdi")
    una = recortar(ALEN, ctx, tipo_de=TIPOS_ALEN).md
    assert not recortar(una, ctx, tipo_de=TIPOS_ALEN).cambia


def test_el_invariante_caza_un_cambio_de_texto():
    assert not solo_cambian_enlaces("Un [disco](/a) bueno.", "Un disco malo.")
    assert not solo_cambian_enlaces("Un disco.", "Un [disco](/a).")  # no añade


# --------------------------------------------------------------------------- #
# Mayúsculas: falsos positivos medidos en el ensayo de prod (26 de 240)
# --------------------------------------------------------------------------- #
def test_un_nombre_propio_no_casa_en_minuscula():
    indice = [_ent("Rock transgresivo", "/extremoduro/rock-transgresivo", "album"),
              _ent("Pasión", "/sellos/pasion", "band")]
    md = "Hacían rock transgresivo con mucha pasión."
    assert autolink_corpus(md, indice) == md


def test_un_nombre_propio_casa_con_su_mayuscula_y_con_articulo_en_minuscula():
    indice = [_ent("Rock transgresivo", "/extremoduro/rock-transgresivo", "album"),
              _ent("La Mancha", "/lugares/la-mancha", "place")]
    md = "Grabaron Rock transgresivo lejos de la Mancha."
    out = autolink_corpus(md, indice, contexto=ContextoEnlazado(
        origen="/x", relaciones=Relaciones({"/x": {"/lugares/la-mancha"},
                                            "/lugares/la-mancha": {"/x"}})))
    assert rutas_del_cuerpo(out) == ["/extremoduro/rock-transgresivo", "/lugares/la-mancha"]


def test_un_tema_en_mayuscula_a_mitad_de_frase_es_otro_nombre():
    ctx = ContextoEnlazado(origen="/x", relaciones=Relaciones(
        {"/x": {"/temas/esperanza"}, "/temas/esperanza": {"/x"}}))
    indice = [_ent("Esperanza", "/temas/esperanza", "theme")]
    assert rutas_del_cuerpo(autolink_corpus("Vivía en Calle Esperanza S/N.", indice,
                                            contexto=ctx)) == []
    assert rutas_del_cuerpo(autolink_corpus("Queda la esperanza.", indice, contexto=ctx)) == [
        "/temas/esperanza"]
    assert rutas_del_cuerpo(autolink_corpus("Esperanza, al final.", indice, contexto=ctx)) == [
        "/temas/esperanza"]


# --------------------------------------------------------------------------- #
# Corchetes anidados en el anchor (12-11-2026)
# --------------------------------------------------------------------------- #
# Los títulos de directo llevan «[En Directo]». Con `[^\]]+` en el anchor, el
# enlace entero era invisible: no contaba para el tope ni se podía recortar, y el
# post de la gira de 1995 se quedó con 7 enlaces en el cuerpo.
PLATERO_1995 = (Path(__file__).parent / "fixtures" / "post_gira_platero_1995_body.md").read_text()


def test_el_anchor_anidado_es_un_enlace():
    md = "Sonó [Tu corazón [En Directo]](/extremoduro/x/tu-corazon-en-directo) al final."
    assert _ENLACE.findall(md) == [("Tu corazón [En Directo]", "/extremoduro/x/tu-corazon-en-directo")]
    assert rutas_del_cuerpo(md) == ["/extremoduro/x/tu-corazon-en-directo"]


def test_el_post_de_1995_cuenta_todos_sus_enlaces():
    assert len(rutas_del_cuerpo(PLATERO_1995)) == 7


def test_el_recorte_deja_el_post_de_1995_en_el_tope():
    r = recortar(PLATERO_1995, ContextoEnlazado(origen="/blog/gira-extremoduro-platero-1995"))
    assert len(rutas_del_cuerpo(r.md)) <= MAX_BODY_LINKS
    assert solo_cambian_enlaces(PLATERO_1995, r.md)
    assert "Correcaminos (Estate al loro) [En Directo]" in r.md  # el texto se queda
    assert not recortar(r.md, ContextoEnlazado(origen="/blog/gira-extremoduro-platero-1995")).cambia


def test_no_enlaza_dentro_de_un_anchor_anidado():
    indice = [_ent("Pepe Botika", "/extremoduro/agila/pepe-botika", "song")]
    md = "[El directo de Pepe Botika [En Directo]](/extremoduro/x/pepe-botika-en-directo)."
    assert autolink_corpus(md, indice) == md


def test_tambien_cuenta_la_imagen_con_corchetes_en_el_alt():
    antes = "![Portada [reedición]](/c.jpg) y [A](/a)."
    assert solo_cambian_enlaces(antes, "![Portada [reedición]](/c.jpg) y A.")
    assert not solo_cambian_enlaces(antes, "![Portada](/c.jpg) y A.")
