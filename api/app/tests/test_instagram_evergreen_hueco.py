"""El evergreen no puede reponer por encima del atasco.

Medido el 13-sep-2026 en prod: entraban 20-23 items por semana y salían 15. La
cola no bajaba nunca de `BACKLOG_THRESHOLD`, así que los 16 posts que un
bloqueo de Meta condenó en agosto no iban a volver jamás — `recover_failed`
respondía "caben 0 sin pasar de 15 en cola", semana tras semana.

El déficit lo ponía el evergreen, que es justo lo que NO caduca.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem, InstagramQueueMedia, VideoClip
from app.services.instagram import config
from scripts.instagram import prepare_evergreen as pe


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    InstagramQueueItem.__table__.create(engine)
    InstagramQueueMedia.__table__.create(engine)
    VideoClip.__table__.create(engine)
    with Session(engine) as s:
        yield s


def _en_cola(db, n: int, *, status="prepared", **kw) -> None:
    for i in range(n):
        base = dict(
            day=date.today(), slot=2, position=i, content_type="quote",
            title=f"Un verso {i}", status=status, attempts=0,
            media_type="IMAGE", media_locked=False,
        )
        base.update(kw)
        db.add(InstagramQueueItem(**base))
    db.commit()


# --------------------------------------------------------------------------- #
# El hueco
# --------------------------------------------------------------------------- #
def test_con_la_cola_vacia_cabe_el_umbral_entero(db):
    assert pe._hueco_de_goteo(db) == config.BACKLOG_THRESHOLD


def test_el_hueco_es_lo_que_falta_no_el_tope(db):
    """Un tope no es un hueco. Devolver el umbral a secas metería 15 encima de
    los que ya estaban, que es justo el atasco que esto viene a evitar."""
    _en_cola(db, 4)
    assert pe._hueco_de_goteo(db) == config.BACKLOG_THRESHOLD - 4


def test_con_la_cola_pasada_de_vueltas_no_cabe_nada(db):
    _en_cola(db, config.BACKLOG_THRESHOLD + 7)
    assert pe._hueco_de_goteo(db) == 0


def test_lo_ya_propuesto_tambien_ocupa_sitio(db):
    """Nacen `proposed` y el admin los aprueba: contarlos solo al aprobarse
    dejaría reponer cada semana sobre un montón que ya estaba esperando."""
    _en_cola(db, 5, status="proposed")
    assert pe._hueco_de_goteo(db) == config.BACKLOG_THRESHOLD - 5


def test_lo_que_tiene_fecha_fija_no_ocupa_hueco_de_goteo(db):
    """Una efeméride sale por `due_pinned` a su día, al margen del cuentagotas:
    no compite por el goteo y no puede consumir su cupo."""
    _en_cola(db, 6, publish_on=date.today() + timedelta(days=30))
    assert pe._hueco_de_goteo(db) == config.BACKLOG_THRESHOLD


def test_lo_condenado_no_ocupa_hueco(db):
    """Un post sin intentos ya no vuelve solo: ocupar sitio con él frenaría la
    reposición sin que nadie llegue a publicarlo."""
    _en_cola(db, 4, status="failed", attempts=config.MAX_PUBLISH_ATTEMPTS)
    assert pe._hueco_de_goteo(db) == config.BACKLOG_THRESHOLD


# --------------------------------------------------------------------------- #
# El recorte
# --------------------------------------------------------------------------- #
_MIX = {"quote": 6, "ephemeris": 4, "anecdote": 4, "robe_quote": 3, "product": 1}


def test_si_cabe_todo_el_mix_no_se_toca():
    assert pe.recortar_al_hueco(_MIX, 99) == _MIX


def test_sin_hueco_no_se_propone_nada_que_gotee():
    out = pe.recortar_al_hueco(_MIX, 0)
    assert out["quote"] == out["anecdote"] == out["robe_quote"] == out["product"] == 0


def test_las_efemerides_sobreviven_al_recorte():
    """Su fecha es la que es: recortarlas pierde el aniversario para siempre."""
    assert pe.recortar_al_hueco(_MIX, 0)["ephemeris"] == 4
    assert pe.recortar_al_hueco(_MIX, 2)["ephemeris"] == 4


def test_el_recorte_reparte_en_vez_de_vaciar_un_tipo():
    """Con hueco 2 se prefiere un verso y una anécdota a dos versos: un lote
    corto no puede salir entero del primer tipo del mix."""
    out = pe.recortar_al_hueco(_MIX, 2)
    gotean = {t: n for t, n in out.items() if t != "ephemeris"}
    assert sum(gotean.values()) == 2
    assert max(gotean.values()) == 1


def test_el_recorte_nunca_pasa_del_hueco():
    for hueco in range(0, 15):
        out = pe.recortar_al_hueco(_MIX, hueco)
        gotean = sum(n for t, n in out.items() if t != "ephemeris")
        assert gotean <= hueco
        assert gotean <= sum(n for t, n in _MIX.items() if t != "ephemeris")
