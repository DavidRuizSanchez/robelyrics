"""El goteo saca primero lo que caduca.

El 13-sep-2026 volvieron a la cola 16 versos y anécdotas que un bloqueo de Meta
había condenado en agosto. Fueron al final, que es lo correcto, pero eso les
daba siete días de calendario por delante de cualquier noticia futura: como
`prepare_daily` encola cada una detrás de todo (`max(position) + 1`), la
actualidad de esa semana habría salido con doce días encima.

Publicar una noticia de doce días engaña sobre cuándo pasó — es la misma razón
por la que `recover_failed` las descarta en vez de repescarlas. Al revés no se
pierde nada: un verso espera.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem, InstagramQueueMedia, VideoClip
from app.services.instagram import publisher


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    InstagramQueueItem.__table__.create(engine)
    InstagramQueueMedia.__table__.create(engine)
    VideoClip.__table__.create(engine)
    with Session(engine) as s:
        yield s


def _item(db, *, content_type, position, slot=1, **kw) -> InstagramQueueItem:
    base = dict(
        day=date.today(), slot=slot, position=position, content_type=content_type,
        title=f"{content_type} en {position}", status="prepared", attempts=0,
        media_type="IMAGE", media_locked=False,
    )
    base.update(kw)
    it = InstagramQueueItem(**base)
    db.add(it)
    db.commit()
    db.refresh(it)
    return it


def test_una_noticia_nueva_no_espera_detras_del_evergreen(db):
    """El caso exacto del 13-sep: 16 versos repescados ocupando la cola y una
    noticia encolada detrás de todos ellos."""
    for i in range(16):
        _item(db, content_type="quote", position=100 + i)
    nueva = _item(db, content_type="news", position=200)
    assert publisher.next_pending(db).id == nueva.id


def test_entre_noticias_sigue_mandando_el_orden_manual(db):
    """Dentro del grupo, `position` manda: es el reordenado a mano del panel."""
    segunda = _item(db, content_type="news", position=5)
    primera = _item(db, content_type="news", position=1)
    assert primera.position < segunda.position
    assert publisher.next_pending(db).id == primera.id


def test_entre_evergreen_tambien_manda_el_orden_manual(db):
    _item(db, content_type="quote", position=9)
    primero = _item(db, content_type="quote", position=2)
    assert publisher.next_pending(db).id == primero.id


def test_el_blog_cuenta_como_actualidad(db):
    """Un post del blog también está atado a su momento."""
    _item(db, content_type="quote", position=1)
    post = _item(db, content_type="blog", position=99)
    assert publisher.next_pending(db).id == post.id


def test_sin_actualidad_sale_el_evergreen(db):
    """Priorizar no es bloquear: si no hay noticias, la cola sigue andando."""
    primero = _item(db, content_type="quote", position=3)
    _item(db, content_type="product", position=7)
    assert publisher.next_pending(db).id == primero.id


def test_el_slot_no_decide_el_orden(db):
    """En prod había `news` repartidas entre los slots 0, 1 y 2: el slot lo pone
    `prepare_daily` por hueco del día, no por tipo. Ordenar por él metería
    noticias detrás de versos."""
    _item(db, content_type="quote", position=50, slot=0)
    noticia = _item(db, content_type="news", position=51, slot=2)
    assert publisher.next_pending(db).id == noticia.id


def test_lo_que_tiene_fecha_fija_sigue_fuera_del_goteo(db):
    """Una efeméride no gotea aunque sea lo primero: sale su día por
    `due_pinned`. Colarla aquí la publicaría antes de tiempo."""
    _item(db, content_type="ephemeris", position=0,
          publish_on=date(2026, 12, 31))
    quote = _item(db, content_type="quote", position=80)
    assert publisher.next_pending(db).id == quote.id
