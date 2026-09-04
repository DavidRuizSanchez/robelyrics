"""Repesca de lo que un bloqueo de Meta condenó.

47 posts quedaron sin intentos en agosto de 2026 por una restricción de cuenta
que no era culpa suya. Lo evergreen vuelve; lo que era actualidad, no: una
noticia de hace tres semanas publicada hoy engaña sobre cuándo pasó.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem, InstagramQueueMedia, VideoClip
from app.services.instagram import config
from scripts.instagram import recover_failed as rf


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    InstagramQueueItem.__table__.create(engine)
    InstagramQueueMedia.__table__.create(engine)
    VideoClip.__table__.create(engine)
    with Session(engine) as s:
        yield s


def _condenado(db, **kw) -> InstagramQueueItem:
    base = dict(
        day=date.today() - timedelta(days=10), slot=1, position=0,
        content_type="quote", title="Un verso", status="failed",
        attempts=config.MAX_PUBLISH_ATTEMPTS,
        error="User access is restricted", error_code="25/2207050",
        last_attempt_at=datetime.now(UTC),
        image_url="https://res.cloudinary.com/x.jpg",
    )
    base.update(kw)
    it = InstagramQueueItem(**base)
    db.add(it)
    db.commit()
    db.refresh(it)
    return it


HOY = date.today()


@pytest.mark.parametrize("tipo", ["quote", "anecdote", "robe_quote", "product"])
def test_lo_evergreen_no_caduca(tipo):
    it = InstagramQueueItem(content_type=tipo, day=HOY - timedelta(days=30))
    assert not rf.caduco(it, HOY)


@pytest.mark.parametrize("tipo", ["news", "blog"])
def test_la_actualidad_caduca(tipo):
    it = InstagramQueueItem(content_type=tipo, day=HOY)
    assert rf.caduco(it, HOY)


def test_una_efemeride_pasada_caduca():
    """Evergreen como tema, pero no como fecha: la del 3 de agosto se vuelve a
    proponer el año que viene, no se publica en septiembre."""
    it = InstagramQueueItem(content_type="ephemeris", day=HOY - timedelta(days=32))
    assert rf.caduco(it, HOY)


def test_una_efemeride_futura_no_caduca():
    it = InstagramQueueItem(
        content_type="ephemeris", day=HOY, publish_on=HOY + timedelta(days=5)
    )
    assert not rf.caduco(it, HOY)


def test_repescar_devuelve_a_la_cola_y_borra_el_rastro(db):
    it = _condenado(db)
    rf._repescar(db, it, cola_al_final=7)
    db.commit()
    assert it.attempts == 0
    assert it.error is None
    assert it.error_code is None
    assert it.last_attempt_at is None
    assert it.position == 7
    # Con la imagen ya en Cloudinary no hay que preparar nada de nuevo.
    assert it.status == "prepared"


def test_repescar_limpia_la_fecha_pasada(db):
    """El riesgo de avalancha: `due_pinned` publica de una tacada TODO lo
    vencido, sin pasar por el cuentagotas. Repescar 24 posts con sus fechas
    viejas los volcaría al feed de golpe."""
    it = _condenado(
        db,
        publish_at=datetime.now(UTC) - timedelta(days=9),
        publish_on=HOY - timedelta(days=9),
    )
    rf._repescar(db, it, cola_al_final=1)
    db.commit()
    assert it.publish_at is None
    assert it.publish_on is None


def test_repescar_respeta_una_fecha_futura(db):
    """Lo programado para dentro de una semana sigue programado."""
    manana = HOY + timedelta(days=7)
    it = _condenado(db, publish_on=manana)
    rf._repescar(db, it, cola_al_final=1)
    db.commit()
    assert it.publish_on == manana


def test_repescar_no_toca_las_urls_de_cloudinary(db):
    """La repesca no cuesta dinero: lo subido sigue subido."""
    it = _condenado(db)
    it.media.append(
        InstagramQueueMedia(position=0, kind="image", url="https://cdn/ya-esta.jpg")
    )
    db.commit()
    rf._repescar(db, it, cola_al_final=1)
    db.commit()
    assert [m.url for m in it.media] == ["https://cdn/ya-esta.jpg"]
    assert it.image_url == "https://res.cloudinary.com/x.jpg"


def test_sin_material_vuelve_como_pending(db):
    """Sin imagen ni fichero hay que volver a prepararlo."""
    it = _condenado(db, image_url=None, image_path=None)
    rf._repescar(db, it, cola_al_final=1)
    db.commit()
    assert it.status == "pending"


def test_solo_se_miran_los_que_agotaron_intentos(db):
    """Los que aún conservan intentos vuelven solos; tocarlos sería colarse."""
    _condenado(db, attempts=config.MAX_PUBLISH_ATTEMPTS - 1)
    vivo = _condenado(db, status="prepared", attempts=0)
    assert vivo.id not in [x.id for x in rf._condenados(db)]
    assert len(rf._condenados(db)) == 0
