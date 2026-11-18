"""Menciones con página que salían sin @id (18-11-2026).

Medido en prod sobre posts y fichas publicadas: 129 menciones con @id y 20 más que
tenían página y salían solo con su nombre. Dos causas:
- Robe (12): el modelo escribe la pista `robe` y la ficha es `robe-iniesta`; con una
  pista que no casaba, no se probaba el nombre.
- Grupos y sellos (8: Fito & Fitipaldis, Platero y Tú, Leño, DRO, El Dromedario,
  Warner): `MusicGroup` solo se buscaba en `artists` (Extremoduro y Robe).
"""
from __future__ import annotations

from app.db.models import Band, Person, SeoContent
from app.services.entity_resolver import resolve_entities
from app.tests.test_person_visibility import db  # noqa: F401  (fixture SQLite)


def _ficha(sesion, tipo, entidad, publicada=True):
    sesion.add(SeoContent(entity_type=tipo, entity_id=entidad.id, slug=entidad.slug, body_md="x",
                      published=publicada, entities=[], secondary_keywords=[], outline=[]))
    sesion.commit()


def _persona(sesion, slug, artistico, completo):
    p = Person(slug=slug, stage_name=artistico, full_name=completo)
    sesion.add(p)
    sesion.flush()
    _ficha(sesion, "person", p)
    return p


def _banda(sesion, slug, nombre, kind="band", publicada=True):
    b = Band(slug=slug, name=nombre, kind=kind)
    sesion.add(b)
    sesion.flush()
    _ficha(sesion, "band", b, publicada)
    return b


def test_robe_con_pista_corta_llega_a_su_ficha(db):  # noqa: F811
    _persona(db, "robe-iniesta", "Robe", "Roberto Iniesta")
    [r] = resolve_entities(db, [{"type": "Person", "name": "Robe", "slug_hint": "robe"}])
    assert r["canonical_id"].endswith("/personas/robe-iniesta#person")


def test_una_pista_de_otra_persona_no_se_salta_por_el_nombre(db):  # noqa: F811
    # El caso Fito Páez: mismo nombre artístico, otra persona.
    _persona(db, "fito-cabrales", "Fito", "Adolfo Cabrales")
    [r] = resolve_entities(db, [{"type": "Person", "name": "Fito", "slug_hint": "fito-paez"}])
    assert r["canonical_id"] is None


def test_grupo_con_ficha_sale_con_su_id(db):  # noqa: F811
    _banda(db, "fito-y-fitipaldis", "Fito & Fitipaldis")
    [r] = resolve_entities(db, [{"type": "MusicGroup", "name": "Fito & Fitipaldis"}])
    assert r["canonical_id"].endswith("/grupos/fito-y-fitipaldis#musicgroup")
    assert r["url"].endswith("/grupos/fito-y-fitipaldis")


def test_sello_va_a_sellos_con_id_de_organizacion(db):  # noqa: F811
    _banda(db, "dro", "DRO", kind="label")
    [r] = resolve_entities(db, [{"type": "Organization", "name": "DRO"}])
    assert r["canonical_id"].endswith("/sellos/dro#organization")


def test_grupo_sin_ficha_publicada_no_se_enlaza(db):  # noqa: F811
    _banda(db, "ciclonautas", "Ciclonautas", publicada=False)
    [r] = resolve_entities(db, [{"type": "MusicGroup", "name": "Ciclonautas"}])
    assert r["canonical_id"] is None
