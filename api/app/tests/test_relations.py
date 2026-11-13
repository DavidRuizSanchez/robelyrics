"""Relaciones con fuente (`entity_relations`, plan de datos estructurados, fase 1)."""
from __future__ import annotations

import pytest

from app.db.models import (
    Album,
    Artist,
    Band,
    BandMembership,
    Book,
    Concept,
    EntityRelation,
    Person,
    Place,
    SeoContent,
    Song,
    SongCredit,
    Theme,
)
from app.services import jsonld_audit as ja
from app.services import relations as rel
from app.tests.test_person_visibility import _con_dependencias

BASE = "https://e.com"


@pytest.fixture()
def db():
    from sqlalchemy import ARRAY, JSON, MetaData, Text, create_engine
    from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
    from sqlalchemy.orm import Session

    md = MetaData()
    modelos = (Person, SeoContent, BandMembership, Artist, Album, Song, SongCredit, Band,
               Place, Theme, Concept, Book, EntityRelation)
    for tabla in _con_dependencias([m.__table__ for m in modelos]):
        t = tabla.to_metadata(md)
        for col in t.columns:
            if isinstance(col.type, (JSONB, ARRAY)):
                # Conservar none_as_null: es lo que deja pasar el CHECK «id o literal».
                col.type = JSON(none_as_null=getattr(col.type, "none_as_null", False))
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


def _ficha(db, tipo, ident, slug):
    db.add(SeoContent(entity_type=tipo, entity_id=ident, slug=slug, body_md="x",
                      published=True, entities=[], secondary_keywords=[], outline=[]))


@pytest.fixture()
def cat(db):
    alen = Person(slug="alen", full_name="Alén Ayerdi")
    oculta = Person(slug="oculta", full_name="Persona Oculta")
    marea = Band(slug="marea", name="Marea", kind="band")
    sin_ficha = Band(slug="sin-ficha", name="Grupo Sin Ficha", kind="band")
    sello = Band(slug="dromedario", name="El Dromedario Records", kind="label")
    extremo = Artist(slug="extremoduro", name="Extremoduro")
    db.add_all([alen, oculta, marea, sin_ficha, sello, extremo,
                Place(slug="plasencia", name="Plasencia", kind="city")])
    db.flush()
    _ficha(db, "person", alen.id, "alen")
    _ficha(db, "band", marea.id, "marea")
    _ficha(db, "band", sello.id, "dromedario")
    db.commit()
    return db


def _p(sujeto, pred, objeto, **kw):
    kw.setdefault("fuentes", [{"kind": "prensa", "tier": "T2", "url": "https://a.es/x",
                               "evidencia": "…"}])
    return rel.Propuesta(sujeto=sujeto, predicado=pred, objeto=objeto, **kw)


def _guardar(db, propuesta):
    errores, fila = rel.validar(db, propuesta, BASE)
    assert not errores, errores
    db.add(EntityRelation(**fila))
    db.commit()
    return fila


# --- Con la tabla vacía no cambia nada ---------------------------------------
def test_tabla_vacia_no_emite_nada(cat):
    for tipo, slug in (("person", "alen"), ("band", "marea"), ("label", "dromedario")):
        ref = rel.resolver_ref(cat, f"{tipo}:{slug}")
        assert rel.jsonld_de(cat, tipo, ref.id, site_url=BASE) is None


def test_lo_pendiente_no_se_emite(cat):
    _guardar(cat, _p("person:alen", "memberOf", "band:marea"))
    alen = rel.resolver_ref(cat, "person:alen")
    assert rel.jsonld_de(cat, "person", alen.id, site_url=BASE) is None


# --- Validación ----------------------------------------------------------------
def test_referencias_desconocidas(cat):
    assert rel.validar(cat, _p("person:nadie", "memberOf", "band:marea"))[0]
    assert rel.validar(cat, _p("person:alen", "memberOf", "band:nada"))[0]
    # un sello no se cita como grupo ni al revés
    assert rel.validar(cat, _p("person:alen", "worksFor", "band:dromedario"))[0]


def test_lo_que_tiene_otra_autoridad_no_se_carga(cat):
    err, _ = rel.validar(cat, _p("person:alen", "memberOf", "artist:extremoduro"))
    assert any("band_memberships" in e for e in err)


def test_vocabulario_en_los_dos_sentidos(cat):
    err, _ = rel.validar(cat, _p("person:alen", "track", "band:marea"))
    assert any("track" in e for e in err)
    # válido directo e inverso
    assert not rel.validar(cat, _p("person:alen", "memberOf", "band:marea"))[0]


def test_verificada_necesita_t1_o_dos_t2(cat):
    un_t2 = _p("person:alen", "memberOf", "band:marea", estado="verificada",
               verificado_por="david")
    assert any("T1 o dos T2" in e for e in rel.validar(cat, un_t2)[0])
    mismo_dominio = _p("person:alen", "memberOf", "band:marea", estado="verificada",
                       verificado_por="david", fuentes=[
                           {"kind": "prensa", "tier": "T2", "url": "https://a.es/1"},
                           {"kind": "prensa", "tier": "T2", "url": "https://www.a.es/2"}])
    assert rel.validar(cat, mismo_dominio)[0]
    dos = _p("person:alen", "memberOf", "band:marea", estado="verificada",
             verificado_por="david", fuentes=[
                 {"kind": "prensa", "tier": "T2", "url": "https://a.es/1"},
                 {"kind": "prensa", "tier": "T2", "url": "https://b.es/2"}])
    assert not rel.validar(cat, dos)[0]
    sin_quien = _p("person:alen", "memberOf", "band:marea", estado="verificada", fuentes=[
        {"kind": "creditos_disco", "tier": "T1", "evidencia": "libreto"}])
    assert any("verificado_por" in e for e in rel.validar(cat, sin_quien)[0])


def test_t1_de_musicbrainz_exige_identidad_acreditada(cat):
    mb = [{"kind": "musicbrainz", "tier": "T1", "url": "https://musicbrainz.org/artist/1"}]
    p = _p("person:alen", "memberOf", "band:marea", estado="verificada",
           verificado_por="david", fuentes=mb)
    err, _ = rel.validar(cat, p)
    assert sum("sin identidad acreditada" in e for e in err) == 2   # sujeto y objeto
    for suj, url in (("person:alen", "https://musicbrainz.org/artist/aaa"),
                     ("band:marea", "https://musicbrainz.org/artist/bbb")):
        _guardar(cat, _p(suj, "sameAs", url, estado="verificada", verificado_por="david",
                         fuentes=[{"kind": "revision_manual", "tier": "T1", "url": url,
                                   "evidencia": "misma entidad"}]))
    assert not rel.validar(cat, p)[0]


def test_literales_pasan_nombre_y_rayas(cat):
    malo = _p("person:alen", "memberOf", {"@type": "MusicGroup", "name": "Banda de Robe Iniesta"})
    assert rel.validar(cat, malo)[0]
    raya = _p("person:alen", "memberOf", {"@type": "MusicGroup", "name": "Uno — Dos"})
    assert rel.validar(cat, raya)[0]
    assert not rel.validar(cat, _p("person:alen", "memberOf",
                                   {"@type": "MusicGroup", "name": "Ciclonautas"}))[0]


def test_sameas_solo_con_url(cat):
    assert rel.validar(cat, _p("person:alen", "sameAs", "Q123"))[0]


# --- Emisión -------------------------------------------------------------------
def test_emite_con_rol_id_canonico_e_inversa(cat):
    _guardar(cat, _p("person:alen", "memberOf", "band:marea", rol="batería", desde="1997",
                     estado="verificada", verificado_por="david", fuentes=[
                         {"kind": "creditos_disco", "tier": "T1", "evidencia": "libreto"}]))
    alen = rel.resolver_ref(cat, "person:alen")
    marea = rel.resolver_ref(cat, "band:marea")
    directo = rel.jsonld_de(cat, "person", alen.id, site_url=BASE)
    assert directo == {"memberOf": [{
        "@type": "OrganizationRole", "roleName": "batería", "startDate": "1997",
        "memberOf": {"@type": "MusicGroup", "@id": f"{BASE}/grupos/marea#musicgroup",
                     "name": "Marea", "url": f"{BASE}/grupos/marea"}}]}
    inverso = rel.jsonld_de(cat, "band", marea.id, site_url=BASE)
    assert inverso["member"][0]["member"]["@id"] == f"{BASE}/personas/alen#person"


def test_sin_pagina_servida_solo_el_nombre(cat):
    _guardar(cat, _p("person:alen", "memberOf", "band:sin-ficha", estado="verificada",
                     verificado_por="david", fuentes=[
                         {"kind": "creditos_disco", "tier": "T1", "evidencia": "libreto"}]))
    alen = rel.resolver_ref(cat, "person:alen")
    out = rel.jsonld_de(cat, "person", alen.id, site_url=BASE)
    assert out == {"memberOf": [{"@type": "MusicGroup", "name": "Grupo Sin Ficha"}]}


def test_sello_con_su_id_de_sello(cat):
    _guardar(cat, _p("label:dromedario", "founder", "person:alen", estado="verificada",
                     verificado_por="david", fuentes=[
                         {"kind": "creditos_disco", "tier": "T1", "evidencia": "x"}]))
    sello = rel.resolver_ref(cat, "label:dromedario")
    assert sello.path == "/sellos/dromedario"
    out = rel.jsonld_de(cat, "label", sello.id, site_url=BASE)
    assert out["founder"][0]["@id"] == f"{BASE}/personas/alen#person"


def test_lo_emitido_pasa_la_auditoria(cat):
    """Lo que sale de la tabla, montado en su nodo, no da fallos de vocabulario,
    nombre ni rayas."""
    t1 = [{"kind": "creditos_disco", "tier": "T1", "evidencia": "x"}]
    for p in (
        _p("person:alen", "memberOf", "band:marea", rol="batería", desde="1997"),
        _p("person:alen", "memberOf", {"@type": "MusicGroup", "name": "Ciclonautas"}),
        _p("person:alen", "worksFor", "label:dromedario", rol="mánager"),
        _p("person:alen", "colleague", "person:oculta"),
        _p("person:alen", "homeLocation", "place:plasencia"),
        _p("label:dromedario", "founder", "person:alen"),
        _p("person:alen", "sameAs", "https://www.wikidata.org/wiki/Q1"),
    ):
        p.estado, p.verificado_por, p.fuentes = "verificada", "david", t1
        _guardar(cat, p)
    for tipo, slug, path, tipo_ld in (("person", "alen", "/personas/alen", "Person"),
                                      ("band", "marea", "/grupos/marea", "MusicGroup"),
                                      ("label", "dromedario", "/sellos/dromedario",
                                       "Organization")):
        ref = rel.resolver_ref(cat, f"{tipo}:{slug}")
        props = rel.jsonld_de(cat, tipo, ref.id, site_url=BASE)
        nodo = {"@context": "https://schema.org", "@type": tipo_ld,
                "@id": f"{BASE}{path}#{rel.TIPOS[tipo][1]}", **props}
        pag = ja.analizar([nodo], path)
        assert ja.problemas_de_pagina(pag, ja.cargar_vocabulario()) == [], (slug, props)


# --- Carga ----------------------------------------------------------------------
def test_la_clave_no_depende_de_nulos():
    a = rel.clave("person", 1, "memberOf", "band", 2, None, None, None)
    assert a == rel.clave("person", 1, "memberOf", "band", 2, None, None, None)
    assert a != rel.clave("person", 1, "memberOf", "band", 2, None, "batería", None)
    lit = rel.clave("person", 1, "memberOf", None, None, {"@type": "MusicGroup", "name": "X"},
                    None, None)
    assert lit.startswith("person:1|memberOf|lit:")


def test_la_carga_es_idempotente_y_no_pisa_lo_verificado(cat):
    from scripts.seed_relaciones import aplicar

    t1 = [{"kind": "creditos_disco", "tier": "T1", "evidencia": "x"}]
    verificada = rel.validar(cat, _p("person:alen", "memberOf", "band:marea",
                                     estado="verificada", verificado_por="david",
                                     fuentes=t1), BASE)[1]
    assert aplicar(cat, [verificada])["nuevas"] == 1
    cat.commit()
    assert aplicar(cat, [verificada])["iguales"] == 1
    pendiente = rel.validar(cat, _p("person:alen", "memberOf", "band:marea"), BASE)[1]
    assert pendiente["clave"] == verificada["clave"]
    assert aplicar(cat, [pendiente])["protegidas"] == 1
    cat.commit()
    assert cat.query(EntityRelation).one().status == "verificada"


def test_el_yaml_real_carga_y_valida():
    from scripts.seed_relaciones import cargar_propuestas

    assert cargar_propuestas(ja.ruta_data("relaciones.yaml")) == []
