"""Enfriamiento de metadatos y frescura del volcado de GSC (20-11-2026)."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.db.models import ContentRevision, PageChange, PageMonitorRun, Post, SeoContent
from app.services import cambios_recientes as cr
from app.tests.test_admin_summary import _con_dependencias

AHORA = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
GOLFA = "/extremoduro/yo-minoria-absoluta/golfa"


@pytest.fixture()
def db():
    from sqlalchemy import ARRAY, JSON, MetaData, Text, create_engine
    from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
    from sqlalchemy.orm import Session

    md = MetaData()
    modelos = (PageChange, PageMonitorRun, ContentRevision, SeoContent, Post)
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
        s.add(PageMonitorRun(id=1))
        s.commit()
        yield s


def _cambio(db, path, campo, hace_dias):
    db.add(PageChange(run_id=1, path=path, campo=campo, severidad="importante",
                      detalle={}, detected_at=AHORA - timedelta(days=hace_dias)))
    db.commit()


def _ficha(db, **kw) -> SeoContent:
    sc = SeoContent(entity_type="song", entity_id=1, slug="golfa", published=True,
                    entities=[], secondary_keywords=[], outline=[],
                    **{"body_md": "Intro.\n\n## La letra\n\nTexto.\n", "meta_title": "Golfa",
                       "meta_description": "La canción.", "h1": "Golfa", **kw})
    db.add(sc)
    db.commit()
    return sc


def _revision(db, sc, hace_dias, **kw):
    db.add(ContentRevision(
        target_kind="seo_content", target_id=sc.id, path=GOLFA,
        created_at=AHORA - timedelta(days=hace_dias),
        **{"body_md": sc.body_md, "meta_title": sc.meta_title,
           "meta_description": sc.meta_description, "h1": sc.h1, **kw}))
    db.commit()


def test_un_title_cambiado_hace_una_semana_enfria_la_pagina(db):
    _cambio(db, GOLFA, "title", 8)
    frio = cr.en_enfriamiento(db, GOLFA, ahora=AHORA)
    assert frio.campo == "title"
    assert frio.hasta.date() == date(2026, 12, 10)
    assert "no se toca hasta el 10-12-2026" in frio.motivo()
    # Con o sin barra final es la misma página.
    assert cr.en_enfriamiento(db, GOLFA + "/", ahora=AHORA) == frio


def test_a_los_28_dias_se_puede_volver_a_tocar(db):
    _cambio(db, GOLFA, "title", 29)
    assert cr.en_enfriamiento(db, GOLFA, ahora=AHORA) is None


def test_cuenta_el_ultimo_cambio_y_solo_los_metadatos(db):
    _cambio(db, GOLFA, "title", 9)
    _cambio(db, GOLFA, "headings", 3)
    _cambio(db, GOLFA, "contenido", 1)      # ampliar el cuerpo no enfría
    _cambio(db, "/extremoduro/agila", "enlaces", 1)
    frias = cr.rutas_en_enfriamiento(db, ahora=AHORA)
    assert set(frias) == {GOLFA}
    assert frias[GOLFA].campo == "headings"
    assert frias[GOLFA].cambiado == AHORA - timedelta(days=3)


def test_la_copia_de_hoy_cubre_el_dia_que_tarda_el_monitor(db):
    """Un camino cambia el title por la mañana; el monitor no lo ve hasta las 06:45 del
    día siguiente. La copia que dejó ese camino ya dice que la página no es la de
    antes, y el segundo camino del día se encuentra la puerta cerrada."""
    sc = _ficha(db, meta_title="Letra de Golfa, de Extremoduro")
    _revision(db, sc, 0, meta_title="Golfa")
    frio = cr.en_enfriamiento(db, GOLFA, ahora=AHORA)
    assert frio.campo == "title" and frio.cambiado == AHORA


def test_una_copia_igual_a_la_pagina_no_enfria(db):
    """Ampliar el cuerpo deja copia, pero si title, description, H1 y headings son los
    mismos no ha cambiado ningún metadato. Y lo revertido tampoco cuenta."""
    sc = _ficha(db)
    _revision(db, sc, 2, body_md="Intro vieja.\n\n## La letra\n\nOtro texto.\n")
    assert cr.en_enfriamiento(db, GOLFA, ahora=AHORA) is None


def test_un_heading_renombrado_se_ve_en_la_copia(db):
    sc = _ficha(db)
    _revision(db, sc, 1, body_md="Intro.\n\n## Golfa: la letra\n\nTexto.\n")
    assert cr.en_enfriamiento(db, GOLFA, ahora=AHORA).campo == "headings"


def test_en_un_post_el_h1_es_su_titulo():
    post = type("P", (), {"meta_title": "T", "meta_description": "D", "title": "Nuevo",
                          "body_md": ""})()
    rev = type("R", (), {"meta_title": "T", "meta_description": "D", "h1": "Viejo",
                         "body_md": ""})()
    assert cr.campo_distinto(rev, post) == "h1"
    rev.h1 = None      # las oportunidades no guardan el H1 de un post: no se compara
    assert cr.campo_distinto(rev, post) is None


def test_un_volcado_viejo_no_protege_nada():
    """El de `ranking_guard` acababa el 02-10 y las consultas de «La vereda de la puerta
    de atrás» nacieron el 03-11: el title nuevo «cubría» todo lo que había que cubrir."""
    hoy = date(2026, 11, 12)
    motivo = cr.volcado_caducado("2026-07-10..2026-10-02", hoy=hoy)
    assert "02-10-2026" in motivo and "41 días" in motivo
    assert cr.volcado_caducado("2026-08-21..2026-11-06", hoy=hoy) is None
    assert cr.volcado_caducado("2026-08-21..2026-10-29", hoy=hoy) is None      # 14 días
    assert cr.volcado_caducado("2026-08-21..2026-10-28", hoy=hoy) is not None
    assert "no dice hasta qué día" in cr.volcado_caducado(None, hoy=hoy)
