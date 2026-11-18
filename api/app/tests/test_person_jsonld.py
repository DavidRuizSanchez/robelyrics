"""Relaciones curadas del JSON-LD de persona (data/person_jsonld.yaml, 10-11-2026)."""
from __future__ import annotations

import pytest

from app.db.models import Artist, Person, Place, SeoContent
from app.services import person_jsonld
from app.tests.test_person_visibility import db  # noqa: F401  (fixture SQLite)


def _persona(sesion, slug, nombre, *, publicada):
    p = Person(slug=slug, full_name=nombre)
    sesion.add(p)
    sesion.flush()
    if publicada:
        sesion.add(SeoContent(entity_type="person", entity_id=p.id, slug=slug, body_md="x",
                              published=True, entities=[], secondary_keywords=[], outline=[]))
    return p


@pytest.fixture()
def catalogo(db):  # noqa: F811
    _persona(db, "robe-iniesta", "Roberto Iniesta", publicada=True)
    _persona(db, "salo", "Gonzalo Muñoz", publicada=True)
    _persona(db, "juano", "Juano", publicada=False)
    db.add(Artist(slug="extremoduro", name="Extremoduro"))
    db.add(Place(slug="plasencia", name="Plasencia", kind="city"))
    db.commit()
    return db


def test_resuelve_referencias_y_quita_las_fuentes(catalogo, monkeypatch):
    monkeypatch.setattr(person_jsonld, "_cargar", lambda: {"x": {
        "colleague": ["person:robe-iniesta", "person:juano"],
        "memberOf": [{"@type": "MusicGroup", "name": "Dosis Letal",
                      "foundingLocation": "place:plasencia", "fuente": "W-10"}],
        "knowsAbout": ["artist:extremoduro"],
    }})
    r = person_jsonld.relaciones(catalogo, "x", site_url="https://e.com")
    robe, juano = r["colleague"]
    assert robe["@id"] == "https://e.com/personas/robe-iniesta#person"
    assert juano == {"@type": "Person", "name": "Juano"}   # sin ficha publicada: sin @id
    assert r["memberOf"][0]["foundingLocation"]["@id"] == "https://e.com/lugares/plasencia#place"
    assert "fuente" not in r["memberOf"][0]
    assert r["knowsAbout"][0]["@id"] == "https://e.com/extremoduro#musicgroup"


def test_una_referencia_rota_no_se_inventa(catalogo, monkeypatch):
    monkeypatch.setattr(person_jsonld, "_cargar", lambda: {"x": {"colleague": ["person:nadie"]}})
    with pytest.raises(ValueError):
        person_jsonld.relaciones(catalogo, "x")


def test_sin_entrada_no_hay_relaciones(catalogo):
    assert person_jsonld.relaciones(catalogo, "quien-no-esta") is None


def test_el_yaml_real_se_carga_y_solo_usa_referencias_conocidas():
    import re

    person_jsonld._cargar.cache_clear()
    datos = person_jsonld._cargar()
    assert {"paco-doniga", "jesus-mateos-brea"} <= set(datos)
    texto = person_jsonld._DATA.read_text(encoding="utf-8")
    for tipo, slug in re.findall(r"\b(person|artist|place):([a-z0-9-]+)", texto):
        assert tipo in ("person", "artist", "place") and slug
