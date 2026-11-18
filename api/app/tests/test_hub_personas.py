"""Las tarjetas del hub dicen lo mismo en todas las personas (10-11-2026)."""
from fastapi import Response

from app.db.models import Artist, BandMembership, Person, SeoContent
from app.routers import public
from app.services import person_jsonld
from app.tests.test_person_visibility import db  # noqa: F401  (fixture SQLite)


def _publicar(sesion, p):
    sesion.add(SeoContent(entity_type="person", entity_id=p.id, slug=p.slug, body_md="x",
                          published=True, entities=[], secondary_keywords=[], outline=[]))


def test_papel_y_anyo_para_todas(db, monkeypatch):  # noqa: F811
    art = Artist(slug="extremoduro", name="Extremoduro")
    william = Person(slug="william-extremoduro", full_name="William")
    brea = Person(slug="jesus-mateos-brea", full_name="Jesús Mateos Brea")
    nadie = Person(slug="sin-datos", full_name="Sin Datos")
    db.add_all([art, william, brea, nadie])
    db.flush()
    db.add(BandMembership(person_id=william.id, artist_id=art.id, role="batería", era="1987",
                          position=7))
    for p in (william, brea, nadie):
        _publicar(db, p)
    db.commit()
    monkeypatch.setattr(person_jsonld, "_cargar", lambda: {"jesus-mateos-brea": {
        "birthDate": "1982", "hasOccupation": [{"name": "muralista"}]}})
    items = {i.slug: i for i in public.public_persons_list(Response(), db)}
    assert items["william-extremoduro"].papel == "Batería de Extremoduro"
    assert items["jesus-mateos-brea"].papel == "Muralista"
    assert items["jesus-mateos-brea"].birth_year == "1982"
    assert items["sin-datos"].papel is None          # sin dato, no se inventa
