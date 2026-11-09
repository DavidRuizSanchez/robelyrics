"""El «Día N sin Robe» es el del día en que SALE el post, no el de prepararlo.

Medido el 09-11-2026: 94 de 140 posts publicados en 60 días llevaban otro número,
hasta 48 días por detrás, porque se calculaba con `date.today()` al preparar.
"""
from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.services.instagram import config, publisher


def _item(caption, publish_on=None, publish_at=None):
    return SimpleNamespace(caption=caption, publish_on=publish_on, publish_at=publish_at)


def test_contador_con_fecha():
    assert config.dias_sin_robe(date(2026, 11, 9)) == 334
    assert config.dias_sin_robe(date(2025, 12, 10)) == 0


def test_fecha_de_publicacion_prefiere_lo_fijado():
    assert publisher.fecha_de_publicacion(_item("", publish_on=date(2026, 12, 31))) == date(2026, 12, 31)
    # 23:30 UTC del 31-12 ya es 1 de enero en Madrid.
    cuando = datetime(2026, 12, 31, 23, 30, tzinfo=UTC)
    assert publisher.fecha_de_publicacion(_item("", publish_at=cuando)) == date(2027, 1, 1)


def test_desfasado_en_el_goteo():
    hoy = date(2026, 11, 9)
    assert publisher.contador_desfasado(_item("🕯️ Día 330 sin Robe"), hoy)
    assert not publisher.contador_desfasado(_item("🕯️ Día 334 sin Robe"), hoy)
    assert not publisher.contador_desfasado(_item("sin contador"), hoy)


def test_programado_para_mas_adelante_no_se_rehace_hoy():
    hoy = date(2026, 11, 9)
    fijado = _item("🕯️ Día 386 sin Robe", publish_on=date(2026, 12, 31))
    assert not publisher.contador_desfasado(fijado, hoy)
    # Pero si salió tarde (el cron estuvo caído), se pone al día.
    atrasado = _item("🕯️ Día 330 sin Robe", publish_on=date(2026, 11, 5))
    assert publisher.contador_desfasado(atrasado, hoy)
