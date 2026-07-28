"""Tests de la autoprogramación de la cola de Instagram.

Lo que tiene que cumplir el reparto automático:
  - no saltarse el techo semanal que impone el cuentagotas,
  - intercalar tipos (que no caigan tres versos seguidos),
  - no pisar huecos ya ocupados ni programar en el pasado,
  - decir qué se queda fuera y por qué, en vez de perderlo en silencio.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem, InstagramQueueMedia
from app.services.instagram import scheduling


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    InstagramQueueItem.__table__.create(engine)
    InstagramQueueMedia.__table__.create(engine)
    with Session(engine) as s:
        yield s


def _add(db, tipo="quote", **kw) -> InstagramQueueItem:
    base = dict(
        day=date.today(), slot=1, position=0, content_type=tipo,
        title=f"Post de {tipo}", status="pending",
    )
    base.update(kw)
    it = InstagramQueueItem(**base)
    db.add(it)
    db.commit()
    db.refresh(it)
    return it


AHORA = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)  # lunes


# --------------------------------------------------------------------------- #
# Reparto básico
# --------------------------------------------------------------------------- #
def test_asigna_fecha_a_los_aprobados_sin_fecha(db):
    for i in range(3):
        _add(db, position=i)
    asignaciones, descartes = scheduling.plan(db, weeks=4, desde=AHORA)
    assert len(asignaciones) == 3
    assert not descartes
    assert all(cuando > AHORA for _, cuando in asignaciones)


def test_no_programa_en_el_pasado(db):
    _add(db)
    asignaciones, _ = scheduling.plan(db, weeks=4, desde=AHORA)
    assert asignaciones[0][1] > AHORA


def test_no_toca_los_que_ya_tienen_fecha(db):
    ya = AHORA + timedelta(days=2)
    _add(db, publish_at=ya)
    asignaciones, _ = scheduling.plan(db, weeks=4, desde=AHORA)
    assert asignaciones == []


def test_no_toca_las_efemerides(db):
    """Una efeméride tiene su día atado al aniversario."""
    _add(db, tipo="ephemeris", publish_on=date(2026, 8, 20))
    asignaciones, _ = scheduling.plan(db, weeks=4, desde=AHORA)
    assert asignaciones == []


def test_no_programa_lo_no_aprobado(db):
    _add(db, status="proposed")
    _add(db, status="discarded")
    asignaciones, _ = scheduling.plan(db, weeks=4, desde=AHORA)
    assert asignaciones == []


def test_dos_posts_nunca_comparten_slot(db):
    for i in range(8):
        _add(db, position=i)
    asignaciones, _ = scheduling.plan(db, weeks=4, desde=AHORA)
    momentos = [c for _, c in asignaciones]
    assert len(momentos) == len(set(momentos))


# --------------------------------------------------------------------------- #
# Techo semanal
# --------------------------------------------------------------------------- #
def test_respeta_el_tope_semanal(db):
    cap = scheduling.cap_semanal()
    for i in range(cap * 3):
        _add(db, position=i)
    asignaciones, _ = scheduling.plan(db, weeks=4, desde=AHORA)

    por_semana: dict = {}
    for _, cuando in asignaciones:
        lunes = scheduling._lunes_de(cuando)
        por_semana[lunes] = por_semana.get(lunes, 0) + 1
    assert por_semana, "no se programó nada"
    assert max(por_semana.values()) <= cap, por_semana


def test_el_tope_sale_del_cuentagotas(db):
    """Una sola fuente de verdad: si cambia el intervalo, cambia el tope."""
    from app.services.instagram import config
    assert scheduling.cap_semanal() == max(
        1, round(24 * 7 / config.STEADY_INTERVAL_H)
    )


def test_lo_ya_programado_ocupa_sitio(db):
    """Si la semana ya está llena a mano, el automático no la sobrecarga."""
    cap = scheduling.cap_semanal()
    for i in range(cap):
        _add(db, position=i, publish_at=AHORA + timedelta(days=1, hours=i))
    nuevo = _add(db, position=99)
    asignaciones, _ = scheduling.plan(db, weeks=1, desde=AHORA)
    for item, cuando in asignaciones:
        if item.id == nuevo.id:
            lunes_ocupado = scheduling._lunes_de(AHORA + timedelta(days=1))
            assert scheduling._lunes_de(cuando) != lunes_ocupado


def test_sin_hueco_se_reporta_el_motivo(db):
    """Nada se pierde en silencio."""
    for i in range(60):
        _add(db, position=i)
    _, descartes = scheduling.plan(db, weeks=1, desde=AHORA)
    assert descartes
    assert all("sin hueco" in d["reason"] for d in descartes)
    assert all("id" in d and "title" in d for d in descartes)


# --------------------------------------------------------------------------- #
# Mezcla editorial
# --------------------------------------------------------------------------- #
def test_intercala_tipos(db):
    """Tres versos seguidos es justo lo que hacía el pipeline viejo."""
    for i in range(3):
        _add(db, tipo="quote", position=i)
    for i in range(3):
        _add(db, tipo="anecdote", position=10 + i)
    asignaciones, _ = scheduling.plan(db, weeks=4, desde=AHORA)
    tipos = [it.content_type for it, _ in asignaciones]
    seguidos = max(
        (sum(1 for _ in grupo) for grupo in __import__("itertools").groupby(tipos)),
        default=0,
    )
    assert seguidos <= 2, f"demasiados del mismo tipo seguidos: {tipos}"


# --------------------------------------------------------------------------- #
# Slots horarios
# --------------------------------------------------------------------------- #
def test_usa_los_slots_configurados(db):
    horas = {h.strftime("%H:%M") for h in scheduling.slots_diarios()}
    for i in range(4):
        _add(db, position=i)
    asignaciones, _ = scheduling.plan(db, weeks=4, desde=AHORA)
    for _, cuando in asignaciones:
        local = cuando.astimezone(scheduling.TZ)
        assert local.strftime("%H:%M") in horas


def test_apply_plan_escribe_las_fechas(db):
    _add(db)
    asignaciones, _ = scheduling.plan(db, weeks=4, desde=AHORA)
    assert scheduling.apply_plan(db, asignaciones) == 1
    assert db.query(InstagramQueueItem).first().publish_at is not None
