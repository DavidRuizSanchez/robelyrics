"""El cortacircuitos: cuando Meta nos bloquea, dejar de gastar.

El 24-ago-2026 Meta restringió la cuenta. Durante once días el cron siguió
disparando cada 15 minutos: subía imágenes a Cloudinary y creaba containers que
Meta rechazaba uno detrás de otro. Nadie se enteró y la cola acabó vacía.

El estado del bloqueo no vive en ningún flag: se deduce de los fallos recientes
de la propia cola, así que caduca solo.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem, InstagramQueueMedia, VideoClip
from app.services.instagram import config, publisher


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    InstagramQueueItem.__table__.create(engine)
    InstagramQueueMedia.__table__.create(engine)
    VideoClip.__table__.create(engine)
    with Session(engine) as s:
        yield s


def _fallo(db, *, code="25/2207050", hace_h=0.0, **kw) -> InstagramQueueItem:
    """Un item que falló hace `hace_h` horas con ese código."""
    base = dict(
        day=date.today(), slot=1, position=0, content_type="quote",
        title="Un verso", status="failed", attempts=1,
        error="User access is restricted", error_code=code,
        last_attempt_at=datetime.now(UTC) - timedelta(hours=hace_h),
    )
    base.update(kw)
    it = InstagramQueueItem(**base)
    db.add(it)
    db.commit()
    db.refresh(it)
    return it


def test_la_cuenta_restringida_abre_el_cortacircuitos_con_un_solo_fallo(db):
    """No hace falta esperar a una racha: 25/2207050 ya dice que es global."""
    _fallo(db)
    bloqueado, motivo, desde = publisher.publicacion_bloqueada(db)
    assert bloqueado
    assert "25/2207050" in motivo
    assert desde is not None


def test_un_solo_post_roto_no_bloquea_nada(db):
    """Un caption de más de 2200 caracteres es culpa suya, no una caída."""
    _fallo(db, code="36004/2207010", error="caption demasiado largo")
    assert publisher.publicacion_bloqueada(db)[0] is False


def test_una_racha_de_desconocidos_si_bloquea(db):
    """La red que hace asumible que un código nuevo gaste intento: si fallan
    varios posts DISTINTOS seguidos, la culpa no es de ninguno de ellos."""
    for i in range(config.GLOBAL_STREAK):
        _fallo(db, code="424242", error="algo nunca visto", position=i)
    bloqueado, motivo, _ = publisher.publicacion_bloqueada(db)
    assert bloqueado
    assert "distintos" in motivo


def test_por_debajo_de_la_racha_no_bloquea(db):
    for i in range(config.GLOBAL_STREAK - 1):
        _fallo(db, code="424242", position=i)
    assert publisher.publicacion_bloqueada(db)[0] is False


def test_el_cortacircuitos_caduca_solo(db):
    """Nadie tiene que acordarse de cerrarlo: pasada la ventana, el siguiente
    intento real hace de sondeo. Son 4 al día en vez de 96."""
    _fallo(db, hace_h=config.BLOCK_WINDOW_H + 1)
    assert publisher.publicacion_bloqueada(db)[0] is False


def test_un_fallo_sin_fecha_no_cuenta(db):
    """Los items que ya estaban en `failed` antes de esta migración tienen
    `last_attempt_at` a NULL: no pueden abrir un bloqueo retroactivo."""
    _fallo(db, last_attempt_at=None)
    assert publisher.publicacion_bloqueada(db)[0] is False


def test_con_el_cortacircuitos_abierto_no_se_sube_nada_a_cloudinary(db, monkeypatch):
    """El test del coste. Cada intento subía imágenes y creaba containers para
    que Meta los rechazara: eso es lo que pasó 96 veces al día durante 11 días."""
    _fallo(db)
    victima = _fallo(db, code=None, error=None, status="prepared", attempts=0,
                     last_attempt_at=None, position=9, image_url="https://cdn/x.jpg")

    def explota(*a, **k):
        raise AssertionError("no se puede tocar Cloudinary con Meta bloqueado")

    monkeypatch.setattr(publisher.cloudinary_upload, "upload", explota)
    monkeypatch.setattr(publisher.cloudinary_upload, "upload_video", explota)
    monkeypatch.setattr(
        publisher.graph_api, "connection_is_healthy", lambda: (True, "OK", "cuenta")
    )
    monkeypatch.setattr(
        publisher.graph_api, "post_photo",
        lambda *a, **k: pytest.fail("tampoco se llama a Meta"),
    )

    res = publisher.publish(db, victima)
    assert res.status == "failed"
    assert "bloqueada" in res.error
    # Y sobre todo: no le cuesta un intento, que es lo que condenó la cola.
    assert res.attempts == 0


def test_force_se_salta_el_cortacircuitos(db, monkeypatch):
    """El botón del panel: un humano tiene que poder ver el error real."""
    _fallo(db)
    victima = _fallo(db, code=None, error=None, status="prepared", attempts=0,
                     last_attempt_at=None, position=9, image_url="https://cdn/x.jpg")
    llamadas = []
    monkeypatch.setattr(
        publisher.graph_api, "connection_is_healthy", lambda: (True, "OK", "cuenta")
    )
    monkeypatch.setattr(
        publisher.graph_api, "post_photo",
        lambda *a, **k: (llamadas.append(1), ("18123", "Publicado"))[1],
    )
    res = publisher.publish(db, victima, force=True)
    assert llamadas, "con force sí se llama a Meta"
    assert res.status == "published"
