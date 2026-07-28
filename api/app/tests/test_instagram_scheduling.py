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


# --------------------------------------------------------------------------- #
# Reparto de formatos: que el feed no salga monótono
# --------------------------------------------------------------------------- #
# Al activar el carrusel por defecto, 26 de los 28 posts de la cola pasaron a
# ser carrusel de golpe. Esto reparte foto / carrusel / reel.

def _prog(db, i, **kw):
    return _add(db, position=i, publish_at=AHORA + timedelta(days=1, hours=i), **kw)


def test_reparte_los_tres_formatos(db):
    for i in range(12):
        _prog(db, i)
    scheduling.repartir_formatos(db, semilla=0)
    formatos = {it.media_type for it in db.query(InstagramQueueItem).all()}
    assert formatos == {"IMAGE", "CAROUSEL", "REELS"}


def test_no_deja_dos_formatos_iguales_seguidos(db):
    for i in range(15):
        _prog(db, i)
    scheduling.repartir_formatos(db, semilla=3)
    items = db.query(InstagramQueueItem).order_by(InstagramQueueItem.publish_at).all()
    tipos = [it.media_type for it in items]
    seguidos = [
        (a, b) for a, b in zip(tipos, tipos[1:]) if a == b
    ]
    assert not seguidos, f"formatos repetidos seguidos: {tipos}"


def test_respeta_el_formato_elegido_a_mano(db):
    fijo = _prog(db, 0, media_type="REELS", media_locked=True)
    for i in range(1, 8):
        _prog(db, i)
    scheduling.repartir_formatos(db, semilla=1)
    db.refresh(fijo)
    assert fijo.media_type == "REELS", "se ha pisado una decisión humana"


def test_es_determinista_con_la_misma_semilla(db):
    for i in range(9):
        _prog(db, i)
    scheduling.repartir_formatos(db, semilla=7)
    primera = [it.media_type for it in
               db.query(InstagramQueueItem).order_by(InstagramQueueItem.id).all()]
    scheduling.repartir_formatos(db, semilla=7)
    segunda = [it.media_type for it in
               db.query(InstagramQueueItem).order_by(InstagramQueueItem.id).all()]
    assert primera == segunda


def test_otra_semilla_da_otro_reparto(db):
    for i in range(9):
        _prog(db, i)
    scheduling.repartir_formatos(db, semilla=0)
    a = [it.media_type for it in
         db.query(InstagramQueueItem).order_by(InstagramQueueItem.id).all()]
    scheduling.repartir_formatos(db, semilla=5)
    b = [it.media_type for it in
         db.query(InstagramQueueItem).order_by(InstagramQueueItem.id).all()]
    assert a != b


def test_el_que_cambia_vuelve_a_pendiente(db):
    """Cambiar de formato obliga a regenerar el material."""
    it = _prog(db, 0, media_type="IMAGE", status="prepared", image_path="/tmp/x.jpg")
    for i in range(1, 6):
        _prog(db, i)
    cambios = scheduling.repartir_formatos(db, semilla=0)
    db.refresh(it)
    if any(c["id"] == it.id for c in cambios):
        assert it.status == "pending"
        assert it.image_path is None


def test_no_toca_lo_que_no_esta_programado(db):
    suelto = _add(db, position=0)          # sin publish_at
    _prog(db, 1)
    scheduling.repartir_formatos(db, semilla=0, solo_programados=True)
    db.refresh(suelto)
    assert suelto.media_type == "IMAGE"


def test_la_mezcla_es_configurable():
    mezcla = scheduling.mezcla_formatos()
    assert mezcla
    assert set(mezcla) <= set(scheduling.FORMATOS_VALIDOS)
