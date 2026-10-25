"""Volver a descargar lo mismo no puede parecer material nuevo (`upsert_source`).

Corre contra Postgres DE VERDAD, porque `ON CONFLICT … DO UPDATE` no existe en el
SQLite de los demás tests. Todo va dentro de una transacción que se deshace al
acabar. Sin Postgres a mano (el CI), se salta.
"""
from __future__ import annotations

import time

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from scripts.research.common import upsert_source


@pytest.fixture
def pg():
    from app.db.session import engine

    try:
        conn = engine.connect()
    except Exception:  # noqa: BLE001
        pytest.skip("sin Postgres")
    trans = conn.begin()
    db = Session(bind=conn)
    try:
        yield db
    finally:
        db.close()
        trans.rollback()
        conn.close()


def _estado(db, sid):
    return db.execute(text("select fetched_at, referenced_song_ids from interpretation_sources "
                           "where id = :i"), {"i": sid}).one()


def _subir(db, texto, **kw):
    return upsert_source(db, kind="forum", url="https://foro.test/hilo#post-test", title="Foro",
                         content_raw=texto, content_clean=texto, quality_score=0.5, **kw)


def test_lo_mismo_otra_vez_no_resella_ni_borra_los_enlaces(pg):
    sid = _subir(pg, "Agila se grabó en Iruña")
    pg.execute(text("update interpretation_sources set referenced_song_ids = '{7}' "
                    "where id = :i"), {"i": sid})        # lo que hace link_sources_to_songs
    antes = _estado(pg, sid)
    time.sleep(0.01)
    assert _subir(pg, "Agila se grabó en Iruña") == sid
    despues = _estado(pg, sid)
    assert despues.fetched_at == antes.fetched_at
    assert despues.referenced_song_ids == [7]


def test_si_cambia_el_texto_si_se_resella(pg):
    sid = _subir(pg, "versión uno")
    antes = _estado(pg, sid)
    time.sleep(0.01)
    _subir(pg, "versión dos, con un dato nuevo")
    assert _estado(pg, sid).fetched_at > antes.fetched_at


def test_unos_enlaces_nuevos_si_cuentan(pg):
    sid = _subir(pg, "texto", referenced_song_ids=[1])
    antes = _estado(pg, sid)
    time.sleep(0.01)
    _subir(pg, "texto", referenced_song_ids=[1, 2])
    despues = _estado(pg, sid)
    assert despues.referenced_song_ids == [1, 2] and despues.fetched_at > antes.fetched_at


def test_un_post_del_foro_conserva_su_clave_aunque_se_mueva_en_el_hilo():
    from scripts.research.fetch_forums import _clave_post

    hilo = "https://foro.test/hilo"
    ya = {"Agila es el mejor disco": f"{hilo}#post-3"}      # clave vieja, por índice
    assert _clave_post(hilo, "Agila es el mejor disco", ya) == f"{hilo}#post-3"
    nueva = _clave_post(hilo, "Un post nuevo", ya)
    assert nueva.startswith(f"{hilo}#post-") and nueva == _clave_post(hilo, "Un post nuevo", {})
