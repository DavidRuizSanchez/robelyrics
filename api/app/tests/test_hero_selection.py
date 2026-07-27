"""Selección del hero por PROTAGONISTA: un post sobre alguien fuera del corpus no
prefiere la foto de una entidad meramente relacionada.
"""
from __future__ import annotations

import app.services.hero_image as him


def test_match_sujeto():
    subj = him._norm_tokens("rosendo mercado pilar del rock")
    robe = {"label": "Robe"}
    rosendo = {"label": "Rosendo Mercado"}
    assert him._subject_match(robe, subj) == 0.0        # Robe no es el sujeto
    assert him._subject_match(rosendo, subj) == 1.0     # Rosendo sí


def test_protagonista_gana_a_entidad_relacionada(monkeypatch):
    # _entity_image devuelve un marcador por slug (sin BD real).
    monkeypatch.setattr(him, "_entity_image",
                        lambda db, etype, slug: {"url": f"img::{slug}", "attribution": slug,
                                                 "license": None, "source": None, "alt": slug})
    entities = [
        {"type": "Person", "slug_hint": "robe-iniesta", "label": "Robe"},
        {"type": "Person", "slug_hint": "rosendo", "label": "Rosendo Mercado"},
    ]
    # Post sobre Rosendo: debe elegir a Rosendo, no a Robe (aunque Robe aparezca).
    img = him.pick_hero_image(None, entities, subject="rosendo mercado")
    assert img["url"] == "img::rosendo"


def test_sin_protagonista_no_bloquea_tematico(monkeypatch):
    # Post temático (ninguna entidad coincide con el sujeto): se permite usar la
    # imagen de una entidad relacionada (la garantía la pone luego el gate).
    monkeypatch.setattr(him, "_entity_image",
                        lambda db, etype, slug: {"url": f"img::{slug}", "attribution": slug,
                                                 "license": None, "source": None, "alt": slug})
    entities = [{"type": "MusicComposition", "slug_hint": "so-payaso", "label": "So payaso"}]
    img = him.pick_hero_image(None, entities, subject="canciones de amor")
    assert img is not None and img["url"] == "img::so-payaso"


def test_dedup_respeta_used(monkeypatch):
    monkeypatch.setattr(him, "_entity_image",
                        lambda db, etype, slug: {"url": f"img::{slug}", "attribution": slug,
                                                 "license": None, "source": None, "alt": slug})
    entities = [{"type": "Person", "slug_hint": "robe-iniesta", "label": "Robe"}]
    # Si la única imagen ya está usada, no la repite: devuelve None.
    assert him.pick_hero_image(None, entities, subject="robe", used={"img::robe-iniesta"}) is None
