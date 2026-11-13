"""Invariantes del JSON-LD servido (fase 0 del plan de datos estructurados).

La fixture `jsonld_linea_base_2026-11-13b.json.gz` es el JSON-LD REAL de las 389
URLs del sitemap rastreadas el 13-11-2026 hacia las 11:36 UTC (`scripts/seo/audit_jsonld.py
--guardar`), tras cargar y pintar las relaciones de la muestra (PR #120): la única pérdida
fueron las 3 líneas del birthPlace en texto de Robe, sustituido por el verificado (David).
Antes: la del 13-11 10:05 (sin los Q-IDs inventados, #117) y la del 12-11, la primera. Con ella, el CI comprueba dos cosas que un caso sintético no prueba:
que el verificador encuentra justo los fallos que había publicados ese día, y que
`data/jsonld_excepciones.yaml` los declara todos y nada más.
"""
from __future__ import annotations

import copy
import gzip
import json
from collections import Counter
from pathlib import Path

import pytest

from app.services import jsonld_audit as ja
from app.services import page_monitor as pm

FIXTURE = Path(__file__).parent / "fixtures" / "jsonld_linea_base_2026-11-13b.json.gz"
S = "https://entreinteriores.com"


@pytest.fixture(scope="module")
def crudo() -> dict:
    return json.loads(gzip.decompress(FIXTURE.read_bytes()))


@pytest.fixture(scope="module")
def paginas(crudo) -> dict[str, ja.Pagina]:
    return {p: ja.analizar(d["bloques"], p) for p, d in crudo.items() if d["status"] == 200}


@pytest.fixture(scope="module")
def voc() -> ja.Vocabulario:
    return ja.cargar_vocabulario()


def _pagina(nodos: list[dict], path: str) -> ja.Pagina:
    return ja.analizar([{"@context": "https://schema.org", "@graph": nodos}], path)


# --------------------------------------------------------------------------- #
# La línea base real
# --------------------------------------------------------------------------- #
def test_linea_base_solo_tiene_los_fallos_declarados(paginas, voc):
    fallos = ja.auditar(paginas, voc)
    nuevos, conocidos, sobran = ja.separar(fallos, ja.cargar_excepciones())
    assert [str(f) for f in nuevos] == []
    assert sobran == []          # una excepción que no cubre nada escondería un regreso
    assert Counter(f.regla for f in conocidos) == {"vocabulario": 154, "colgante": 72}


def test_la_huella_congelada_es_la_de_la_fixture(paginas):
    """`data/jsonld/linea_base.json` y la fixture son el mismo rastreo: si alguien
    cambia cómo se calcula la huella, la línea base deja de servir y hay que saberlo."""
    base = json.loads(ja.ruta_data("jsonld/linea_base.json").read_text())
    assert base["urls"] == len(paginas) == 389
    for path, huella in base["huellas"].items():
        assert sorted(paginas[path].huella) == huella, path


def test_alen_ayerdi_ya_marca_sus_grupos(paginas):
    """El caso que abrió el plan (A-01): el 12-11 Alén solo marcaba nombre, URL e
    imagen. Desde el 13-11 (#120) marca su identidad y sus grupos, con fuente."""
    pag = paginas["/personas/alen-ayerdi"]
    props = {linea.split(" ", 2)[1] for linea in pag.huella
             if linea.startswith("/personas/alen-ayerdi#person ")}
    assert {"memberOf", "sameAs"} <= props
    assert any(l.endswith("memberOf → /grupos/marea#musicgroup") for l in pag.huella)


# --------------------------------------------------------------------------- #
# Contención
# --------------------------------------------------------------------------- #
def test_quitar_una_relacion_es_una_perdida(crudo):
    path = next(p for p, d in sorted(crudo.items())
                if p.startswith("/personas/") and '"memberOf"' in json.dumps(d["bloques"]))
    antes = ja.analizar(crudo[path]["bloques"], path)
    bloques = copy.deepcopy(crudo[path]["bloques"])
    for nodo in ja.raices(bloques):
        nodo.pop("memberOf", None)
    salen = ja.perdidas(antes.huella, ja.analizar(bloques, path).huella)
    # Se pierde la relación y también el nodo del grupo que iba anidado dentro.
    assert f"{path}#person memberOf → /extremoduro#musicgroup" in salen
    assert "/extremoduro#musicgroup name" in salen


def test_cambiar_un_literal_o_el_orden_no_es_perdida():
    nodo = {"@type": "Person", "@id": f"{S}/personas/x#person", "name": "Uno",
            "sameAs": ["https://a", "https://b"],
            "memberOf": [{"@id": f"{S}/extremoduro#musicgroup"}, {"@id": f"{S}/robe#musicgroup"}]}
    otro = {**nodo, "name": "Otro", "sameAs": ["https://b"],
            "memberOf": list(reversed(nodo["memberOf"]))}
    assert ja.perdidas(_pagina([nodo], "/personas/x").huella,
                       _pagina([otro], "/personas/x").huella) == []


def test_perder_un_id_es_perdida_aunque_quede_la_propiedad():
    nodo = {"@type": "Person", "@id": f"{S}/personas/x#person",
            "memberOf": [{"@id": f"{S}/extremoduro#musicgroup"}, {"@id": f"{S}/robe#musicgroup"}]}
    otro = {**nodo, "memberOf": [{"@id": f"{S}/robe#musicgroup"}]}
    assert ja.perdidas(_pagina([nodo], "/personas/x").huella,
                       _pagina([otro], "/personas/x").huella) == [
        "/personas/x#person memberOf → /extremoduro#musicgroup"]


# --------------------------------------------------------------------------- #
# @id colgantes
# --------------------------------------------------------------------------- #
def test_id_colgante_y_definido():
    grupo = _pagina([{"@type": "MusicGroup", "@id": f"{S}/grupos/marea#musicgroup",
                      "name": "Marea"}], "/grupos/marea")
    persona = _pagina([{"@type": "Person", "@id": f"{S}/personas/x#person",
                        "memberOf": [{"@id": f"{S}/grupos/marea#musicgroup"},
                                     {"@id": f"{S}/grupos/marea#organization"},
                                     {"@id": f"{S}/sellos/nada#organization"},
                                     {"@id": "https://www.wikidata.org/wiki/Q1"}]}],
                      "/personas/x")
    fallos = ja.ids_colgantes({"/grupos/marea": grupo, "/personas/x": persona})
    assert [f.detalle for f in fallos] == [
        "/grupos/marea#organization (no está definido en /grupos/marea)",
        "/sellos/nada#organization (la página /sellos/nada no está)",
    ]


def test_un_id_relativo_se_resuelve_en_su_pagina():
    pag = _pagina([{"@type": "WebPage", "@id": "#webpage", "breadcrumb": {"@id": "#miga"}}],
                  "/temas/x")
    assert [f.detalle for f in ja.ids_colgantes({"/temas/x": pag})] == [
        "/temas/x#miga (no está definido en /temas/x)"]


# --------------------------------------------------------------------------- #
# Vocabulario
# --------------------------------------------------------------------------- #
def _vocab(nodos, voc, path="/x"):
    return [f.detalle for f in ja.vocabulario(_pagina(nodos, path), voc)]


def test_vocabulario_tipo_y_propiedad_que_no_existen(voc):
    fallos = _vocab([{"@type": "Persona", "name": "x"},
                     {"@type": "Person", "manager": "Alén"}], voc)
    assert any("el tipo Persona no existe" in f for f in fallos)
    assert any("la propiedad manager no existe" in f for f in fallos)


def test_vocabulario_dominio_y_rango(voc):
    fallos = _vocab([
        {"@type": "MusicGroup", "@id": f"{S}/robe#musicgroup",
         "mentions": [{"@id": f"{S}/blog/x#article"}]},
        {"@type": "MusicAlbum", "@id": f"{S}/extremoduro/agila#musicalbum",
         "track": [{"@type": "MusicComposition", "name": "So payaso"}]},
    ], voc)
    assert any("mentions no vale para MusicGroup" in f for f in fallos)
    assert any("track → MusicComposition fuera de rango" in f for f in fallos)


def test_vocabulario_admite_role_herencia_y_acciones(voc):
    assert _vocab([
        {"@type": "Person", "memberOf": [{"@type": "OrganizationRole", "roleName": "batería",
                                          "startDate": "1997",
                                          "memberOf": {"@type": "MusicGroup", "name": "Marea"}}]},
        {"@type": "MusicAlbum", "track": [{"@type": "MusicRecording", "name": "So payaso"}],
         "name": "Agila"},
        {"@type": "WebSite", "potentialAction": {
            "@type": "SearchAction", "target": "https://x/buscar?q={q}",
            "query-input": "required name=q"}},
    ], voc) == []


# --------------------------------------------------------------------------- #
# Nombre y rayas
# --------------------------------------------------------------------------- #
def test_nombre_vetado_y_rayas():
    pag = _pagina([{"@type": "Person", "name": "Roberto Iniesta",
                    "alternateName": ["Robe", "Robe Iniesta"],
                    "sameAs": ["https://es.wikipedia.org/wiki/Robe_Iniesta"],
                    "description": "Músico — y poeta"}], "/personas/robe-iniesta")
    fallos = ja.nombre_y_rayas(pag)
    assert [(f.regla, f.detalle.split(": ", 1)[1]) for f in fallos] == [
        ("nombre", "«Robe Iniesta»"), ("rayas", "«Músico — y poeta»")]


# --------------------------------------------------------------------------- #
# Excepciones
# --------------------------------------------------------------------------- #
def test_excepcion_que_ya_no_cubre_nada_se_avisa():
    exc = [ja.Excepcion("colgante", "/blog/*", r"^/blog#blog", "m", "fase 2"),
           ja.Excepcion("vocabulario", "/robe", "mentions", "m", "fase 2")]
    f = ja.Fallo("colgante", "/blog/x", "/blog#blog (no está definido en /blog)")
    nuevos, conocidos, sobran = ja.separar([f, ja.Fallo("rayas", "/a", "x")], exc)
    assert conocidos == [f] and [n.regla for n in nuevos] == ["rayas"]
    assert [e.paths for e in sobran] == ["/robe"]


# --------------------------------------------------------------------------- #
# Monitor diario
# --------------------------------------------------------------------------- #
def _html(nodos) -> str:
    ld = json.dumps({"@context": "https://schema.org", "@graph": nodos})
    return (f"<html><head><title>x</title><script type='application/ld+json'>{ld}"
            "</script></head><body><main><h1>x</h1></main></body></html>")


def _foto(nodos, path="/personas/x"):
    return {"status": 200, "final_url": S + path, "cadena": [], "ms": 10,
            "campos": pm.parse(_html(nodos), path=path)}


PERSONA = {"@type": "Person", "@id": f"{S}/personas/x#person", "name": "X",
           "memberOf": [{"@id": f"{S}/extremoduro#musicgroup"}]}


def test_monitor_avisa_de_lo_que_se_pierde_y_de_los_fallos_nuevos():
    sin_grupo = {k: v for k, v in PERSONA.items() if k != "memberOf"}
    cambios = {c.campo: c for c in pm.diff(_foto([PERSONA]),
                                           _foto([{**sin_grupo, "manager": "Y"}]),
                                           path="/personas/x")}
    assert cambios["jsonld_perdido"].severidad == "estructural"
    assert cambios["jsonld_perdido"].detalle["salen"] == [
        "/personas/x#person memberOf → /extremoduro#musicgroup"]
    assert any("manager no existe" in x for x in cambios["jsonld_fallo"].detalle["entran"])


def test_monitor_no_compara_con_una_foto_que_no_guardaba_la_huella():
    vieja = _foto([PERSONA])
    for k in ("jsonld_huella", "jsonld_definidos", "jsonld_problemas"):
        vieja["campos"].pop(k)
    campos = [c.campo for c in pm.diff(vieja, _foto([]), path="/personas/x")]
    assert not [c for c in campos if c.startswith("jsonld_")]
    assert pm.diff(_foto([PERSONA]), _foto([PERSONA]), path="/personas/x") == []


def test_monitor_colgantes_solo_los_nuevos():
    from types import SimpleNamespace

    from scripts.seo.monitor_cambios import cruzados_nuevos

    def foto(path, nodos):
        return SimpleNamespace(status=200, campos=pm.parse(_html(nodos), path=path))

    grupo = [{"@type": "MusicGroup", "@id": f"{S}/extremoduro#musicgroup", "name": "E"}]
    ayer = {"/extremoduro": foto("/extremoduro", grupo),
            "/personas/x": foto("/personas/x", [{**PERSONA, "colleague": {
                "@id": f"{S}/personas/fantasma#person"}}])}
    hoy = {"/extremoduro": foto("/extremoduro", grupo),
           "/personas/x": foto("/personas/x", [{**PERSONA, "colleague": [
               {"@id": f"{S}/personas/fantasma#person"},
               {"@id": f"{S}/sellos/nada#organization"}]}])}
    # El fantasma ya colgaba ayer: solo avisa del sello.
    assert {p: [str(f) for f in fs] for p, fs in cruzados_nuevos(ayer, hoy).items()} == {
        "/personas/x": ["[colgante] /personas/x: "
                        "/sellos/nada#organization (la página /sellos/nada no está)"]}


def test_monitor_no_da_por_colgante_lo_que_apunta_a_una_pagina_sin_respuesta():
    from types import SimpleNamespace

    from scripts.seo.monitor_cambios import cruzados_nuevos

    hoy = {"/personas/x": SimpleNamespace(status=200, campos=pm.parse(_html([PERSONA]),
                                                                      path="/personas/x")),
           "/extremoduro": TimeoutError("la red")}
    assert cruzados_nuevos({}, hoy) == {}


def test_rango_de_una_referencia_a_otra_pagina():
    """El caso real de `track`: el tipo de la pista solo lo dice la página de la canción."""
    disco = _pagina([{"@type": "MusicAlbum", "@id": f"{S}/extremoduro/agila#musicalbum",
                      "track": [{"@id": f"{S}/extremoduro/agila/so-payaso#musiccomposition"}]}],
                    "/extremoduro/agila")
    cancion = _pagina([{"@type": "MusicComposition",
                        "@id": f"{S}/extremoduro/agila/so-payaso#musiccomposition"}],
                      "/extremoduro/agila/so-payaso")
    paginas = {"/extremoduro/agila": disco, "/extremoduro/agila/so-payaso": cancion}
    voc = ja.cargar_vocabulario()
    assert ja.vocabulario(disco, voc) == []          # sola, la página no lo puede saber
    assert [f.detalle for f in ja.rangos_cruzados(paginas, voc)] == [
        "/extremoduro/agila#musicalbum: track → MusicComposition fuera de rango "
        "(ItemList/MusicRecording)"]


def test_el_monitor_ve_el_rango_entre_paginas():
    from types import SimpleNamespace

    from scripts.seo.monitor_cambios import cruzados_nuevos

    def foto(path, nodos):
        return SimpleNamespace(status=200, campos=pm.parse(_html(nodos), path=path))

    cancion = [{"@type": "MusicComposition", "@id": f"{S}/robe/x/y#musiccomposition"}]
    disco = [{"@type": "MusicAlbum", "@id": f"{S}/robe/x#musicalbum",
              "track": [{"@id": f"{S}/robe/x/y#musiccomposition"}]}]
    hoy = {"/robe/x": foto("/robe/x", disco), "/robe/x/y": foto("/robe/x/y", cancion)}
    # Sin pasada anterior se descuentan las excepciones: la de `track` cubre /*/*.
    assert cruzados_nuevos({}, hoy) == {}
    hoy = {"/libros/x": foto("/libros/x", [{"@type": "Book", "@id": f"{S}/libros/x#book",
                                             "author": {"@id": f"{S}/robe/x#musicalbum"}}]),
           "/robe/x": foto("/robe/x", [{"@type": "MusicAlbum", "@id": f"{S}/robe/x#musicalbum"}])}
    assert [f.detalle for f in cruzados_nuevos({}, hoy)["/libros/x"]] == [
        "/libros/x#book: author → MusicAlbum fuera de rango (Organization/Person)"]
