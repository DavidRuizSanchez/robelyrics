"""Una persona sin ficha publicada no existe para el público (10-11-2026).

Dar de alta a alguien en `persons` para preparar su ficha la publicaba al
instante: 200 en /personas/<slug> con solo Wikidata, el hub, los miembros del
grupo, el buscador y el autolink. Estos tests fijan que todos esos caminos
tiran de `person_visibility` y que los créditos de coros no son autoría.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import select

from app.db.models import (
    Album,
    Artist,
    Band,
    BandMembership,
    Concept,
    Person,
    Place,
    SeoContent,
    Song,
    SongCredit,
    Theme,
)
from app.routers import public
from app.services.person_visibility import ids_publicadas, persona_publicada
from app.tests.test_admin_summary import _con_dependencias


@pytest.fixture()
def db():
    from sqlalchemy import ARRAY, JSON, MetaData, Text, create_engine
    from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
    from sqlalchemy.orm import Session

    md = MetaData()
    modelos = (Person, SeoContent, BandMembership, Artist, Album, Song, SongCredit,
               Band, Place, Theme, Concept)
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


def _persona(db, slug, nombre, *, publicada):
    p = Person(slug=slug, full_name=nombre)
    db.add(p)
    db.flush()
    if publicada is not None:
        db.add(SeoContent(entity_type="person", entity_id=p.id, slug=slug, body_md="x",
                          published=publicada, entities=[], secondary_keywords=[], outline=[]))
    db.flush()
    return p


@pytest.fixture()
def personas(db):
    kaito = _persona(db, "kaito", "Kaíto", publicada=True)
    angel = _persona(db, "angel-lorenzo", "Ángel Lorenzo", publicada=False)  # borrador
    sin_ficha = _persona(db, "maria-timon", "María Timón", publicada=None)
    db.commit()
    return kaito, angel, sin_ficha


def test_solo_cuenta_la_ficha_publicada(db, personas):
    kaito, angel, sin_ficha = personas
    visibles = db.execute(select(Person.slug).where(persona_publicada())).scalars().all()
    assert visibles == ["kaito"]
    assert ids_publicadas(db) == {kaito.id}


def test_el_hub_no_ensena_borradores(db, personas):
    slugs = [p.slug for p in public.public_persons_list(Response(), db)]
    assert slugs == ["kaito"]


@pytest.mark.parametrize("slug", ["angel-lorenzo", "maria-timon"])
def test_la_ficha_sin_publicar_da_404(db, personas, slug):
    with pytest.raises(HTTPException) as e:
        public.public_person_detail(slug, Response(), db)
    assert e.value.status_code == 404


def test_un_credito_solo_enlaza_a_ficha_publicada(db, personas):
    kaito, angel, sin_ficha = personas
    art = Artist(slug="extremoduro", name="Extremoduro")
    db.add(art)
    db.flush()
    alb = Album(slug="deltoya", title="Deltoya", year=1992, artist_id=art.id)
    db.add(alb)
    db.flush()
    song = Song(slug="papel-secante", title="Papel secante", album_id=alb.id)
    db.add(song)
    db.flush()
    db.add_all([
        SongCredit(song_id=song.id, person_id=None, credit_role="voces", credited_name="María Timón"),
        SongCredit(song_id=song.id, person_id=angel.id, credit_role="colaboracion", credited_name="Ángel Lorenzo"),
        SongCredit(song_id=song.id, person_id=None, credit_role="colaboracion", credited_name="Kaíto"),
    ])
    db.commit()
    creditos = {c.name: c for c in public._credits_for_song(db, song.id)}
    assert creditos["María Timón"].person_slug is None      # sin ficha
    assert creditos["Ángel Lorenzo"].person_slug is None    # ficha en borrador
    assert creditos["Kaíto"].person_slug == "kaito"         # publicada, por nombre
    assert creditos["María Timón"].role_label == "Voces"
    # La autoría va primero; coros y voces, detrás.
    assert [c.role for c in public._credits_for_song(db, song.id)][-1] == "voces"


def test_el_autolink_no_enlaza_borradores(db, personas, monkeypatch):
    from app.services import entity_resolver

    monkeypatch.setattr(entity_resolver, "_corpus_index", None, raising=False)
    indice = entity_resolver.build_corpus_index(db)
    urls = " ".join(str(v) for v in (indice.values() if isinstance(indice, dict) else indice))
    assert "/personas/kaito" in urls
    assert "/personas/angel-lorenzo" not in urls
    assert "/personas/maria-timon" not in urls


def test_seed_de_coros_es_idempotente_y_enlaza_si_hay_ficha(db, personas):
    from scripts.seed_vocal_credits import sembrar

    art = Artist(slug="extremoduro", name="Extremoduro")
    db.add(art)
    db.flush()
    alb = Album(slug="somos-unos-animales", title="Somos unos animales", year=1991, artist_id=art.id)
    db.add(alb)
    db.flush()
    db.add(Song(slug="desidia", title="Desidia", album_id=alb.id))
    db.commit()
    entradas = [{"album_slug": "somos-unos-animales", "role": "coros", "literal": "x",
                 "names": ["María Timón", "Belén"], "songs": ["desidia", "no-existe"]}]
    primera = sembrar(db, entradas)
    segunda = sembrar(db, entradas)
    assert primera == {"insertados": 2, "ya_estaban": 0, "canciones_no_encontradas": 1}
    assert segunda == {"insertados": 0, "ya_estaban": 2, "canciones_no_encontradas": 1}
    filas = db.execute(select(SongCredit)).scalars().all()
    assert {(c.credited_name, c.credit_role, c.source) for c in filas} == {
        ("María Timón", "coros", "wikipedia"), ("Belén", "coros", "wikipedia")}
    # María Timón tiene fila en persons (sin ficha): se enlaza por id igualmente;
    # que se VEA lo decide person_visibility, no el seed.
    assert next(c for c in filas if c.credited_name == "María Timón").person_id == personas[2].id


def test_el_verificador_no_ve_el_fondo_sin_corroborar(monkeypatch):
    """`generate_deep` pasaba al verificador el material con el fondo dentro."""
    from types import SimpleNamespace

    from app.services import corpus_for_queries
    from scripts.seo import generate_deep

    material = ("[LETRA de «X»]\nverso propio\n\n----\n\n"
                "[TRANSCRIPCIÓN de YouTube] Paco tocó en 1983 en el campo de fútbol\n\n----\n\n"
                "[blog] Dato de un blog")
    visto = {}

    def falso_corroborar(client, fondo, propio, consultas, **kw):
        visto["fondo"], visto["propio"] = fondo, propio
        return ["Dosis Letal se formó en 1983"], ["Dato de un blog"]

    monkeypatch.setattr(corpus_for_queries, "corroborar", falso_corroborar)
    monkeypatch.setattr(generate_deep, "log", lambda *a, **k: None)
    dossier = SimpleNamespace(hard_facts="HECHOS DUROS", material=material, subject="Paco Doniga")
    afirmable = generate_deep._material_afirmable(None, dossier, ["Paco Doniga"])
    assert "campo de fútbol" in visto["fondo"] and "verso propio" not in visto["fondo"]
    assert "verso propio" in afirmable and "HECHOS DUROS" in afirmable
    assert "campo de fútbol" not in afirmable and "Dato de un blog" not in afirmable
    assert "Dosis Letal se formó en 1983" in afirmable


def _formacion(db, kaito, angel):
    art = Artist(slug="extremoduro", name="Extremoduro")
    db.add(art)
    db.flush()
    db.add_all([
        BandMembership(artist_id=art.id, person_id=kaito.id, role="bajo", era="1989-1991",
                       position=2),
        BandMembership(artist_id=art.id, person_id=angel.id, role="batería", era="1987",
                       position=1),
    ])
    db.commit()
    return art


def test_la_formacion_nombra_sin_enlazar_a_quien_no_tiene_ficha(db, personas):
    """Ángel Lorenzo fue el primer batería y no tiene ficha: sin él, la formación de
    1987 era un dato falso. Sale, pero sin enlace (criterio de David, 11-11-2026)."""
    kaito, angel, _ = personas
    art = _formacion(db, kaito, angel)
    linea = {m.slug: m for m in public._lineup_for_album(db, art.id, 1987)}
    assert linea["angel-lorenzo"].has_page is False
    linea = {m.slug: m for m in public._lineup_for_album(db, art.id, 1990)}
    assert linea["kaito"].has_page is True and "angel-lorenzo" not in linea


def test_el_dossier_de_una_persona_lee_sus_creditos(db, personas):
    from app.services.deep_research import _creditos_de_persona

    _, angel, sin_ficha = personas
    art = Artist(slug="extremoduro", name="Extremoduro")
    db.add(art)
    db.flush()
    alb = Album(slug="deltoya", title="Deltoya", year=1992, artist_id=art.id)
    db.add(alb)
    db.flush()
    song = Song(slug="papel-secante", title="Papel secante", album_id=alb.id)
    db.add(song)
    db.flush()
    db.add_all([
        SongCredit(song_id=song.id, person_id=None, credit_role="coros", credited_name="María Timón"),
        SongCredit(song_id=song.id, person_id=angel.id, credit_role="musica", credited_name="Á. L."),
    ])
    db.commit()
    hechos = _creditos_de_persona(db, sin_ficha, "María Timón")
    assert hechos == ["María Timón canta coros (interpretación, no autoría) en: "
                      "«Papel secante» (Deltoya, 1992)."]
    # Por person_id aunque el nombre acreditado sea otro.
    assert "«Papel secante»" in _creditos_de_persona(db, angel, "Ángel Lorenzo")[0]


def test_la_vara_de_persona_lleva_su_papel(db, personas):
    from app.services.person_jsonld import papeles

    kaito, angel, _ = personas
    _formacion(db, kaito, angel)
    assert papeles(db, angel) == ["batería en Extremoduro"]
