"""El aviso que no existía.

Instagram estuvo once días parado sin que nada sonara. Estos tests fijan cuándo
suena y —tan importante— cuándo se calla, para que el aviso no acabe siendo
ruido diario que se filtra a la papelera.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem, InstagramQueueMedia, NotificationDigest, VideoClip
from app.services.instagram import config
from scripts.instagram import notify_health as nh


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    for t in (InstagramQueueItem, InstagramQueueMedia, VideoClip, NotificationDigest):
        t.__table__.create(engine)
    with Session(engine) as s:
        yield s


def _item(db, **kw) -> InstagramQueueItem:
    base = dict(
        day=date.today(), slot=1, position=0, content_type="quote",
        title="Un verso", status="pending",
    )
    base.update(kw)
    it = InstagramQueueItem(**base)
    db.add(it)
    db.commit()
    db.refresh(it)
    return it


def _hace(horas: float) -> datetime:
    return datetime.now(UTC) - timedelta(hours=horas)


def test_avisa_con_la_cuenta_restringida(db):
    _item(db, status="failed", attempts=1, error="User access is restricted",
          error_code="25/2207050", last_attempt_at=_hace(1))
    _item(db, status="published", published_at=_hace(2), position=1)
    problemas = nh._problemas(nh._gather(db))
    assert any("bloqueando" in p for p in problemas)


def test_avisa_a_los_dos_dias_sin_publicar_con_cola_llena(db):
    """El escenario exacto de agosto, y el detector que no depende de reconocer
    ningún código: cubre el cron muerto, docker caído o un bug nuestro."""
    _item(db, status="published", published_at=_hace(config.ALERT_STALE_H + 5))
    _item(db, status="prepared", position=1)
    problemas = nh._problemas(nh._gather(db))
    assert any("sin publicar" in p for p in problemas)


def test_no_avisa_si_acaba_de_publicar(db):
    _item(db, status="published", published_at=_hace(2))
    _item(db, status="prepared", position=1)
    assert nh._problemas(nh._gather(db)) == []


def test_no_confunde_parado_con_sin_material(db):
    """Sin cola no hay avería: es que falta contenido, y se dice con esas
    palabras en vez de gritar que Instagram está roto."""
    _item(db, status="published", published_at=_hace(config.ALERT_STALE_H + 5))
    problemas = nh._problemas(nh._gather(db))
    assert any("cola está vacía" in p for p in problemas)
    assert not any("sin publicar" in p for p in problemas)


def test_avisa_de_los_que_agotaron_intentos(db):
    _item(db, status="published", published_at=_hace(1))
    _item(db, status="failed", attempts=config.MAX_PUBLISH_ATTEMPTS, position=1,
          last_attempt_at=_hace(50))
    problemas = nh._problemas(nh._gather(db))
    assert any("agotaron sus intentos" in p for p in problemas)


def test_sin_haber_publicado_nunca_tambien_avisa(db):
    """Una instalación nueva no puede quedarse muda para siempre porque
    `published_at` sea NULL en toda la tabla."""
    it = _item(db, status="prepared")
    it.created_at = _hace(config.ALERT_STALE_H + 10)
    db.commit()
    assert any("sin publicar" in p for p in nh._problemas(nh._gather(db)))


# --------------------------------------------------------------------------- #
# Anti-spam
# --------------------------------------------------------------------------- #
def test_la_firma_no_cambia_solo_porque_pase_el_tiempo(db):
    """Dentro del mismo tramo no hay correo nuevo: si no, sonaría cada mañana."""
    _item(db, status="published", published_at=_hace(24 * 2 + 1))
    _item(db, status="prepared", position=1)
    a = nh._signature(nh._gather(db))
    db.query(InstagramQueueItem).filter_by(status="published").update(
        {"published_at": _hace(24 * 2 + 20)}
    )
    db.commit()
    assert nh._signature(nh._gather(db)) == a


def test_la_firma_cambia_al_escalar_de_tramo(db):
    _item(db, status="published", published_at=_hace(24 * 2 + 1))
    _item(db, status="prepared", position=1)
    a = nh._signature(nh._gather(db))
    db.query(InstagramQueueItem).filter_by(status="published").update(
        {"published_at": _hace(24 * 7 + 1)}
    )
    db.commit()
    assert nh._signature(nh._gather(db)) != a


def test_los_tramos_van_por_escalones():
    assert nh._tramo(0.5) == 0
    assert nh._tramo(2.4) == 2
    assert nh._tramo(6.9) == 4
    assert nh._tramo(40) == 30


def test_no_se_envia_si_todo_va_bien(db):
    _item(db, status="published", published_at=_hace(1))
    _item(db, status="prepared", position=1)
    data = nh._gather(db)
    enviar, motivo = nh._should_send(db, nh._problemas(data), nh._signature(data))
    assert not enviar
    assert motivo == "Instagram va bien"


def test_repite_el_aviso_a_los_tres_dias(db):
    _item(db, status="failed", attempts=1, error_code="25/2207050",
          last_attempt_at=_hace(1))
    data = nh._gather(db)
    firma = nh._signature(data)
    problemas = nh._problemas(data)

    db.add(NotificationDigest(kind=nh._KIND, signature=firma, sent_at=_hace(24)))
    db.commit()
    assert nh._should_send(db, problemas, firma)[0] is False

    db.query(NotificationDigest).update(
        {"sent_at": _hace(24 * (nh.REMINDER_DAYS + 1))}
    )
    db.commit()
    enviar, motivo = nh._should_send(db, problemas, firma)
    assert enviar
    assert "recordatorio" in motivo
