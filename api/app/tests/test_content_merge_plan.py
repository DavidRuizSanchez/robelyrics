"""Aplicar un reparto: un destino, una fusión, y todo o nada (26-10-2026).

Caso real (Kabezabolo): dos grupos de la misma propuesta acababan en la misma
página. `aplicar_plan` llamaba a `start_merge` por grupo; el primero creaba la
oportunidad y hacía commit, y el segundo chocaba con «ya hay una ampliación en
curso». El plan quedaba a medias: un grupo fundido y el otro no.
"""
from __future__ import annotations

import pytest
from sqlalchemy import ARRAY, JSON, MetaData, Text, create_engine
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Session

from app.db.models import ContentProposal, SeoContent, SeoOpportunity
from app.services import content_merge as cm
from app.services import content_placement as cp
from app.services.seo_opportunities import MAX_PREPARE_ATTEMPTS


def _con_dependencias(tablas):
    pendientes, vistas = list(tablas), {}
    while pendientes:
        t = pendientes.pop()
        if t.name in vistas:
            continue
        vistas[t.name] = t
        pendientes.extend(fk.column.table for fk in t.foreign_keys)
    return list(vistas.values())


@pytest.fixture()
def db():
    md = MetaData()
    for tabla in _con_dependencias([ContentProposal.__table__, SeoOpportunity.__table__,
                                        SeoContent.__table__]):
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


PAGINAS = {"ficha:1": "/kabezabolo", "ficha:2": "/grupos/platero-y-tu"}


@pytest.fixture(autouse=True)
def _destinos(monkeypatch):
    def fake(_db, target):
        path = PAGINAS.get(target)
        return cp.Candidate(path=path, kind="ficha", label=path, target=target,
                            entity_type="artist", entity_id=7) if path else None
    monkeypatch.setattr(cp, "candidate_for_target", fake)


def _propuesta(db) -> ContentProposal:
    p = ContentProposal(
        kind="evergreen", title="Kabezabolo y Extremoduro", status="proposed",
        target_keyword="kabezabolo extremoduro",
        keywords=[{"keyword": "kabezabolo extremoduro", "volume": 90},
                  {"keyword": "kabezabolo robe", "volume": 40},
                  {"keyword": "kabezabolo letras", "volume": 30},
                  {"keyword": "platero y tu robe", "volume": 20}])
    db.add(p)
    db.commit()
    return p


def test_dos_grupos_a_la_misma_pagina_son_una_sola_fusion(db):
    p = _propuesta(db)
    opps = cm.aplicar_plan(db, p, [
        {"keywords": ["kabezabolo extremoduro"], "target": "ficha:1"},
        {"keywords": ["kabezabolo robe", "kabezabolo letras"], "target": "ficha:1"},
    ])
    assert len(opps) == 1
    assert [q["query"] for q in opps[0].queries] == [
        "kabezabolo extremoduro", "kabezabolo robe", "kabezabolo letras"]
    assert db.query(SeoOpportunity).count() == 1
    activas = cp.proposal_keywords(p)
    assert activas == ["platero y tu robe"]   # lo que no se fundió sigue en la idea


def test_destino_ocupado_no_escribe_nada(db):
    p = _propuesta(db)
    db.add(SeoOpportunity(path="/grupos/platero-y-tu", action="merge", status="drafted",
                          entity_type="band", entity_id=3))
    db.commit()
    with pytest.raises(cm.MergeError, match="platero-y-tu"):
        cm.aplicar_plan(db, p, [
            {"keywords": ["kabezabolo extremoduro"], "target": "ficha:1"},
            {"keywords": ["platero y tu robe"], "target": "ficha:2"},
        ])
    db.refresh(p)
    assert db.query(SeoOpportunity).count() == 1          # solo la que ya estaba
    assert not any(k.get("excluded") for k in p.keywords)  # el plan no quedó a medias
    assert p.status == "proposed"


def test_una_fusion_fallida_sin_reintentos_ya_no_ocupa_la_pagina(db):
    p = _propuesta(db)
    db.add(SeoOpportunity(path="/kabezabolo", action="merge", status="failed",
                          entity_type="artist", entity_id=7,
                          attempts=MAX_PREPARE_ATTEMPTS))
    db.commit()
    opps = cm.aplicar_plan(db, p, [{"keywords": ["kabezabolo robe"], "target": "ficha:1"}])
    assert len(opps) == 1


def test_una_fusion_fallida_con_reintentos_ocupa_y_dice_como_liberarla(db):
    p = _propuesta(db)
    db.add(SeoOpportunity(path="/kabezabolo", action="merge", status="failed",
                          entity_type="artist", entity_id=7, attempts=1))
    db.commit()
    with pytest.raises(cm.MergeError, match="descártala"):
        cm.aplicar_plan(db, p, [{"keywords": ["kabezabolo robe"], "target": "ficha:1"}])


def test_las_keywords_de_descarga_no_cuentan():
    class _P:
        target_keyword = "descargar discografia extremoduro"
        keywords = [{"keyword": "descargar discografia extremoduro"},
                    {"keyword": "extremoduro discografia mega"},
                    {"keyword": "cuantas canciones tiene extremoduro"}]
    assert cp.proposal_keywords(_P()) == ["cuantas canciones tiene extremoduro"]


def test_destino_en_codigo_recomienda_quitar_no_escribir():
    placement = {"decision": "ampliar", "recommended": None,
                 "candidates": [{"path": "/discografia/extremoduro", "target": None,
                                 "mergeable": False}]}
    rec = [o["value"] for o in cp.selector_options(placement) if o["recommended"]]
    assert rec == ["skip"]
