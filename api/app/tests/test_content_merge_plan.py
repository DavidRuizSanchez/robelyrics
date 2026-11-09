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


# --------------------------------------------------------------------------- #
# Cerrar por noop (09-11-2026): Kabezabolo se intentó 4 veces y Ariel Rot 2, porque
# `release_proposal` devolvía las búsquedas y el reparto volvía a la misma página.
# --------------------------------------------------------------------------- #
def _fusion(db, p, kws, target="ficha:1"):
    [opp] = cm.aplicar_plan(db, p, [{"keywords": kws, "target": target}])
    opp.status = "noop"
    opp.error = "no hay nada propio que mejore esta página"
    return opp


def test_un_noop_sin_material_tacha_las_busquedas_y_cierra_la_idea(db):
    p = _propuesta(db)
    opp = _fusion(db, p, ["kabezabolo extremoduro", "kabezabolo robe", "kabezabolo letras",
                          "platero y tu robe"])
    cm.cerrar_por_noop(db, opp, "sin_plan")
    db.commit()
    db.refresh(p)
    assert p.status == "discarded"
    for k in p.keywords:
        assert k["excluded"] is True and k["excluded_reason"] == "sin_plan"
        assert k["noop_path"] == "/kabezabolo" and "merged" not in k
    assert p.placement["last_merge"]["cerrada"] is True
    assert cp.proposal_keywords(p) == []


def test_si_quedan_busquedas_de_otro_grupo_la_idea_sigue_con_ellas(db):
    p = _propuesta(db)
    opp = _fusion(db, p, ["kabezabolo extremoduro", "kabezabolo robe"])
    cm.cerrar_por_noop(db, opp, "no_mejora")
    db.commit()
    db.refresh(p)
    assert p.status == "proposed"
    assert cp.proposal_keywords(p) == ["kabezabolo letras", "platero y tu robe"]
    assert p.target_keyword == "kabezabolo letras"


def test_el_grupo_cerrado_desaparece_del_panel(db):
    p = _propuesta(db)
    p.placement = {"groups": [
        {"keywords": ["kabezabolo extremoduro", "kabezabolo robe"], "recommended": "ficha:1"},
        {"keywords": ["kabezabolo letras", "platero y tu robe"], "recommended": None}]}
    db.commit()
    opp = _fusion(db, p, ["kabezabolo extremoduro", "kabezabolo robe"])
    cm.cerrar_por_noop(db, opp, "sin_plan")
    assert [g["keywords"] for g in p.placement["groups"]] == [
        ["kabezabolo letras", "platero y tu robe"]]


def test_las_tachadas_por_noop_no_vuelven_a_proponerse(db):
    from app.services.keyword_research import kw_slug

    p = _propuesta(db)
    opp = _fusion(db, p, ["kabezabolo robe"])
    cm.cerrar_por_noop(db, opp, "sin_material")
    db.commit()
    # `keyword_research._published_kw_slugs` descarta toda keyword `excluded`.
    excluidas = {kw_slug(k["keyword"]) for k in p.keywords if k.get("excluded")}
    assert kw_slug("kabezabolo robe") in excluidas


def test_un_descarte_manual_sigue_devolviendo_las_busquedas(db):
    p = _propuesta(db)
    opp = _fusion(db, p, ["kabezabolo robe"])
    opp.status = "discarded"
    cm.release_proposal(db, opp)
    db.commit()
    db.refresh(p)
    assert "kabezabolo robe" in cp.proposal_keywords(p)
    assert not any(k.get("noop_path") for k in p.keywords)


def test_recuperar_una_idea_cerrada_reactiva_sus_busquedas_sin_su_pagina(db):
    p = _propuesta(db)
    opp = _fusion(db, p, [k["keyword"] for k in p.keywords])
    cm.cerrar_por_noop(db, opp, "sin_plan")
    p.status = "proposed"
    assert cm.reabrir_cerradas(p) is True
    assert len(cp.proposal_keywords(p)) == 4
    assert cm.paginas_vetadas(p)["kabezabolo robe"] == "/kabezabolo"


def test_reactivar_a_mano_conserva_la_pagina_vetada(db):
    p = _propuesta(db)
    opp = _fusion(db, p, ["kabezabolo robe"])
    cm.cerrar_por_noop(db, opp, "sin_plan")
    cm.excluir_keywords(p, [])
    k = next(k for k in p.keywords if k["keyword"] == "kabezabolo robe")
    assert "excluded" not in k and "excluded_reason" not in k
    assert k["noop_path"] == "/kabezabolo"


def test_el_reparto_no_vuelve_a_la_pagina_que_dio_noop():
    rutas = [("kabezabolo robe", cp.Ruta("/kabezabolo", "entidad", "nombra a Kabezabolo")),
             ("platero y tu robe", cp.Ruta("/grupos/platero-y-tu", "entidad", "x"))]
    out = dict(cp.vetar_rutas(rutas, {"kabezabolo robe": "/kabezabolo"}))
    assert out["kabezabolo robe"].path is None
    assert "ya se intentó" in out["kabezabolo robe"].motivo
    assert out["platero y tu robe"].path == "/grupos/platero-y-tu"


def test_una_evaluacion_que_recomendaba_la_pagina_vetada_pasa_a_nuevo():
    cand = cp.Candidate(path="/kabezabolo", kind="ficha", label="K", target="ficha:1",
                        entity_type="artist", entity_id=7)
    pl = cp.Placement(decision="ampliar", confidence="media", recommended="ficha:1",
                      reasons=["parecido"], candidates=[cand])
    cp._sin_vetadas(pl, {"/kabezabolo"})
    assert pl.decision == "nuevo" and pl.recommended is None and pl.candidates == []
