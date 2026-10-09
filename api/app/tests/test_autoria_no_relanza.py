"""Las erratas de autoría no pueden volver cada noche (09-10-2026).

Medido en prod: el 7-oct se rechazaron seis erratas de autoría y el 8-oct el
barrido de las 03:50 abrió las mismas seis con id nuevo. Y la noche siguiente a
rechazar «Tomás Rodríguez» en «Última Generación», una pasada con suerte lo
aplicó. Causa: `errata_exists` solo miraba las abiertas, y el barrido re-verificaba
todo lo `pending_verification` cada noche con un veredicto que no es reproducible.
"""
from __future__ import annotations

import pytest
from sqlalchemy import JSON, MetaData, Text, create_engine
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Session

from app.db.models import ErrataReport, Song
from app.services import consensus as mcv
from app.services import curated_overrides as co
from app.services import errata_fix as ef
from app.tests.test_errata_fix import _FakeDB, _Result


@pytest.fixture()
def db():
    md = MetaData()
    t = ErrataReport.__table__.to_metadata(md)
    for col in t.columns:
        if isinstance(col.type, JSONB):
            col.type = JSON()
        elif isinstance(col.type, TSVECTOR):
            col.type = Text()
        sd = col.server_default
        if sd is not None and "::" in str(getattr(sd, "arg", "")):
            col.server_default = None
    t.foreign_keys.clear()
    for c in t.columns:
        c.foreign_keys.clear()
    t.constraints = {c for c in t.constraints if not c.__class__.__name__.startswith("ForeignKey")}
    t.indexes.clear()
    engine = create_engine("sqlite://")
    md.create_all(engine)
    with Session(engine) as s:
        yield s


def _add(db, status, right="Marcos Ana (autoría)", target_id=16, field="credit",
         target_type="authorship"):
    db.add(ErrataReport(target_type=target_type, target_id=target_id, field=field,
                        reported_wrong="atribución actual a Robe", suggested_right=right,
                        status=status, reporter="authorship_consensus"))
    db.commit()


def test_rechazada_no_se_reabre(db):
    _add(db, "rejected")
    assert mcv.errata_exists(db, target_type="authorship", target_id=16, field="credit",
                             suggested_right="Marcos Ana (autoría)")


def test_rechazar_una_correccion_no_silencia_otra(db):
    _add(db, "rejected", right="verso A", target_type="song_lyrics", field="lyrics_line")
    assert not mcv.errata_exists(db, target_type="song_lyrics", target_id=16,
                                 field="lyrics_line", suggested_right="verso B")


def test_aplicada_no_cuenta_como_existente(db):
    _add(db, "applied")
    assert not mcv.errata_exists(db, target_type="authorship", target_id=16, field="credit",
                                 suggested_right="Marcos Ana (autoría)")


def test_errata_rejected_es_por_correccion(db):
    _add(db, "rejected", right="Tomás Rodríguez (autoría)", target_id=30)
    assert mcv.errata_rejected(db, target_type="authorship", target_id=30, field="credit",
                               suggested_right="Tomás Rodríguez (autoría)")
    assert not mcv.errata_rejected(db, target_type="authorship", target_id=30, field="credit",
                                   suggested_right="Otro (autoría)")


def test_las_seis_hipotesis_no_entran_al_barrido():
    co.song_credits.cache_clear()
    hip = [e["song_title"] for e in co.song_credits() if e.get("status") == "hipotesis"]
    assert len(hip) == 6
    pend = {e["song_title"] for e in co.pending_only(co.song_credits())}
    assert not pend & set(hip)


def test_arreglar_una_hipotesis_la_cierra_sin_verificar(monkeypatch):
    def _no_verifiques(*a, **kw):
        raise AssertionError("una hipótesis no se re-verifica")

    from scripts.verify import authorship_consensus as ac
    monkeypatch.setattr(ac, "verify_credit", _no_verifiques)
    co.song_credits.cache_clear()
    song = Song(id=78, title="Salir")
    e = ErrataReport(id=29, target_type="authorship", target_id=78, field="credit",
                     reported_wrong="atribución actual a Robe",
                     suggested_right="Santos Isidro Seseña (autoría)", status="needs_human")
    out = ef._fix_authorship(_FakeDB(objects={("Song", 78): song},
                                     results=[_Result(many=[])]), e)
    assert out.closed and e.status == "rejected"
    assert "hipótesis" in e.resolution_note.lower()
