"""Tests de la programación y la aprobación de la cola de Instagram.

Cubren tres cosas que antes no existían:
  - `publish_at`: programar un post a fecha Y hora (no solo día suelto).
  - Todo nace `proposed`: nada se publica sin que el admin lo apruebe.
  - El cuentagotas, que con el cron disparando cada 15 min es lo ÚNICO que
    limita el ritmo de publicación.
"""
from __future__ import annotations

import importlib
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem, InstagramQueueMedia, VideoClip
from app.services.instagram import config, publisher


@pytest.fixture()
def db():
    """SQLite en memoria con solo la tabla de la cola."""
    engine = create_engine("sqlite://")
    InstagramQueueItem.__table__.create(engine)
    InstagramQueueMedia.__table__.create(engine)
    # `next_pending` mira si el clip de un post ya está listo, así que la
    # tabla tiene que existir aunque estos tests no usen clips.
    VideoClip.__table__.create(engine)
    with Session(engine) as s:
        yield s


def _add(db, **kw) -> InstagramQueueItem:
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


# --------------------------------------------------------------------------- #
# publish_at: programación exacta
# --------------------------------------------------------------------------- #
def test_programado_no_entra_en_el_goteo(db):
    """Un post con hora fijada no puede salir por el cuentagotas."""
    _add(db, publish_at=datetime.now(timezone.utc) + timedelta(days=1))
    assert publisher.next_pending(db) is None


def test_sin_programar_si_entra_en_el_goteo(db):
    it = _add(db)
    assert publisher.next_pending(db) is not None
    assert publisher.next_pending(db).id == it.id


def test_programado_vencido_sale(db):
    it = _add(db, publish_at=datetime.now(timezone.utc) - timedelta(minutes=5))
    assert [x.id for x in publisher.due_pinned(db)] == [it.id]


def test_programado_futuro_no_sale_todavia(db):
    _add(db, publish_at=datetime.now(timezone.utc) + timedelta(hours=2))
    assert publisher.due_pinned(db) == []


def test_programado_atrasado_no_se_pierde(db):
    """Si el cron no corrió a su hora, sale en la pasada siguiente."""
    it = _add(db, publish_at=datetime.now(timezone.utc) - timedelta(days=3))
    assert [x.id for x in publisher.due_pinned(db)] == [it.id]


def test_efemerides_siguen_funcionando(db):
    """`publish_on` (día suelto) convive con `publish_at`."""
    it = _add(db, publish_on=date.today(), content_type="ephemeris")
    assert [x.id for x in publisher.due_pinned(db)] == [it.id]
    assert publisher.next_pending(db) is None


def test_publicado_no_se_reprograma(db):
    _add(db, status="published",
         publish_at=datetime.now(timezone.utc) - timedelta(hours=1))
    assert publisher.due_pinned(db) == []


# --------------------------------------------------------------------------- #
# Aprobación obligatoria
# --------------------------------------------------------------------------- #
def test_por_defecto_nace_proposed(monkeypatch):
    """Antes las noticias entraban directas a `pending` y se publicaban sin
    que nadie las viera."""
    monkeypatch.delenv("IG_AUTO_APPROVE", raising=False)
    importlib.reload(config)
    assert config.estado_inicial() == "proposed"


def test_flag_de_escape_devuelve_el_automatismo(monkeypatch):
    monkeypatch.setenv("IG_AUTO_APPROVE", "true")
    importlib.reload(config)
    assert config.estado_inicial() == "pending"
    monkeypatch.delenv("IG_AUTO_APPROVE", raising=False)
    importlib.reload(config)


def test_proposed_no_se_publica(db):
    """Ni por goteo ni por programación: sin aprobar, no sale."""
    _add(db, status="proposed")
    _add(db, status="proposed",
         publish_at=datetime.now(timezone.utc) - timedelta(hours=1))
    assert publisher.next_pending(db) is None
    assert publisher.due_pinned(db) == []


# --------------------------------------------------------------------------- #
# Cadencia: con el cron cada 15 min, el guard es el único límite
# --------------------------------------------------------------------------- #
def test_la_cadencia_da_entre_10_y_12_posts_por_semana(monkeypatch):
    monkeypatch.delenv("IG_STEADY_INTERVAL_H", raising=False)
    importlib.reload(config)
    por_semana = 24 * 7 / config.STEADY_INTERVAL_H
    assert 10 <= por_semana <= 12, (
        f"{por_semana:.1f} posts/semana con STEADY={config.STEADY_INTERVAL_H}h; "
        "el objetivo acordado son 10-12"
    )


# --------------------------------------------------------------------------- #
# Reintentos: un fallo transitorio no puede borrar un post del calendario
# --------------------------------------------------------------------------- #
def test_failed_con_intentos_de_sobra_vuelve_a_la_cola(db):
    """El caso del clip de la sala Vértigo: programado, falló al publicar y
    desapareció. `failed` no era terminal por decisión, sino porque los dos
    selectores filtraban por pending/prepared."""
    it = _add(db, status="failed", attempts=1,
              publish_at=datetime.now(timezone.utc) - timedelta(minutes=5))
    assert [x.id for x in publisher.due_pinned(db)] == [it.id]


def test_failed_en_el_goteo_tambien_vuelve(db):
    it = _add(db, status="failed", attempts=0)
    assert publisher.next_pending(db).id == it.id


def test_failed_sin_intentos_se_queda_fuera(db):
    """Agotados los intentos sí para: si no, un post roto de verdad se
    reintentaría cada 15 minutos para siempre."""
    _add(db, status="failed", attempts=config.MAX_PUBLISH_ATTEMPTS,
         publish_at=datetime.now(timezone.utc) - timedelta(minutes=5))
    _add(db, status="failed", attempts=config.MAX_PUBLISH_ATTEMPTS)
    assert publisher.due_pinned(db) == []
    assert publisher.next_pending(db) is None


def test_un_fallo_del_item_gasta_intento(db):
    it = _add(db, status="prepared")
    publisher._marcar_fallo(db, it, "Cloudinary: lo que sea")
    assert it.status == "failed"
    assert it.attempts == 1
    assert "Cloudinary" in it.error


def test_un_fallo_global_no_gasta_intento(db):
    """Si lo que está caído es la conexión con Meta, el post no tiene la culpa:
    quemarle intentos condenaría a la cola entera por algo que no es suyo."""
    it = _add(db, status="prepared")
    for _ in range(5):
        publisher._marcar_fallo(db, it, "token caducado", quema_intento=False)
    assert it.attempts == 0
    assert [x.id for x in [publisher.next_pending(db)]] == [it.id]
