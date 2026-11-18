"""Un Q-ID que escribió el modelo no se publica (13-11-2026).

Medido sobre lo servido el 12-11: 68 de 157 Q-IDs eran falsos (Extremoduro como un
asteroide, Plasencia como el transporte público de Calgary). Los escribía el modelo
porque el prompt se lo pedía («Q-ID si lo conoces») y `resolve_entities` los
publicaba como `sameAs`, y como `@id` si la entidad no era nuestra.
"""
from __future__ import annotations

from app.db.models import Artist
from app.services import voice
from app.services.entity_resolver import resolve_entities
from app.tests.test_person_visibility import db  # noqa: F401  (fixture SQLite)


def test_entidad_ajena_con_qid_sale_solo_con_su_nombre(db):  # noqa: F811
    [r] = resolve_entities(db, [{"type": "MusicGroup", "name": "Grupo Inventado",
                                 "wikidata_id": "Q157604"}])   # (881) Athene, un asteroide
    assert r["same_as"] == []
    assert r["canonical_id"] is None
    assert r["name"] == "Grupo Inventado"


def test_entidad_nuestra_con_qid_inventado_no_lo_arrastra(db):  # noqa: F811
    db.add(Artist(slug="extremoduro", name="Extremoduro"))
    db.commit()
    [r] = resolve_entities(db, [{"type": "MusicGroup", "name": "Extremoduro",
                                 "wikidata_id": "Q5971", "slug_hint": "extremoduro"}])
    assert r["canonical_id"].endswith("/extremoduro#musicgroup")
    assert r["same_as"] == []


def test_el_prompt_ya_no_pide_identificadores():
    assert "wikidata_id" not in voice._RULES_ENTITIES
    assert "Q-ID si lo conoces" not in voice._RULES_ENTITIES
