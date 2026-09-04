"""Tests del digest de revisión: que solo suene cuando hay algo que hacer.

El correo diario repetía cada mañana exactamente lo mismo (las mismas erratas y
las mismas «auto-correcciones de las últimas 24h», que en realidad eran de hace
días re-selladas por el barrido nocturno). La firma de contenido es lo que corta
ese ruido, y su propiedad crítica es ser ESTABLE con el paso del tiempo.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.models import ErrataReport, NotificationDigest
from scripts import notify_review as nr

# Anclado al reloj real, no a una fecha escrita a mano: `_should_send` compara
# `sent_at` contra `datetime.now()`, así que con un _NOW fijo el test empezaba a
# fallar solo al pasar DIGEST_REMINDER_DAYS de la fecha en que se escribió (se vio
# el 04-09-2026: el digest "de ayer" tenía 39 días y disparaba el recordatorio).
_NOW = datetime.now(timezone.utc)


class _DB:
    """Devuelve el último digest guardado (lo único que _should_send consulta)."""

    def __init__(self, last: NotificationDigest | None = None):
        self._last = last

    def execute(self, _stmt):
        db = self

        class _R:
            def scalar_one_or_none(self_inner):
                return db._last

        return _R()


def _data(errata_ids=(1,), posts=0, watermark=_NOW - timedelta(days=3)) -> dict:
    return {
        "erratas": [ErrataReport(id=i, target_type="catalog", status="needs_human") for i in errata_ids],
        "posts_pending": posts,
        "autofixes": [],
        "watermark": watermark,
    }


def _digest(signature: str, *, days_ago: float = 1) -> NotificationDigest:
    return NotificationDigest(kind="review", signature=signature,
                              sent_at=_NOW - timedelta(days=days_ago))


# --- Firma ------------------------------------------------------------------ #
def test_la_firma_no_cambia_solo_porque_pase_el_tiempo():
    """Clave del anti-spam: mismo estado pendiente → misma firma."""
    assert nr._signature(_data()) == nr._signature(_data())


def test_la_firma_cambia_con_una_errata_nueva():
    assert nr._signature(_data(errata_ids=(1,))) != nr._signature(_data(errata_ids=(1, 2)))


def test_la_firma_cambia_al_resolverse_una_errata():
    assert nr._signature(_data(errata_ids=(1, 2))) != nr._signature(_data(errata_ids=(2,)))


def test_la_firma_cambia_con_una_autocorreccion_nueva():
    a = _data(watermark=_NOW - timedelta(days=3))
    b = _data(watermark=_NOW)
    assert nr._signature(a) != nr._signature(b)


def test_la_firma_cambia_con_posts_nuevos_por_revisar():
    assert nr._signature(_data(posts=16)) != nr._signature(_data(posts=17))


# --- Decisión de envío ------------------------------------------------------ #
def test_sin_nada_pendiente_no_se_manda_nada():
    vacio = {"erratas": [], "posts_pending": 0, "autofixes": [], "watermark": None}
    send, why = nr._should_send(_DB(), vacio, nr._signature(vacio))
    assert send is False and "nada pendiente" in why


def test_una_autocorreccion_sola_no_justifica_un_correo():
    """Si el sistema se lo ha arreglado todo él, no hay nada que pedirle al humano:
    la corrección queda en el feed de auditoría, no en la bandeja de entrada."""
    solo_autofix = {
        "erratas": [], "posts_pending": 0,
        "autofixes": [object()], "watermark": _NOW,
    }
    send, why = nr._should_send(_DB(), solo_autofix, nr._signature(solo_autofix))
    assert send is False and "nada pendiente" in why


def test_el_primer_digest_se_manda():
    data = _data()
    send, why = nr._should_send(_DB(None), data, nr._signature(data))
    assert send is True and "primer" in why


def test_no_se_repite_lo_mismo_al_dia_siguiente():
    data = _data()
    sig = nr._signature(data)
    send, why = nr._should_send(_DB(_digest(sig, days_ago=1)), data, sig)
    assert send is False and "lo mismo" in why


def test_una_novedad_rompe_el_silencio():
    ayer = nr._signature(_data(errata_ids=(1,)))
    hoy = _data(errata_ids=(1, 2))
    send, why = nr._should_send(_DB(_digest(ayer, days_ago=1)), hoy, nr._signature(hoy))
    assert send is True and "novedades" in why


def test_a_las_dos_semanas_se_recuerda_lo_pendiente():
    """Lo pendiente no debe caerse del radar por estar callados."""
    data = _data()
    sig = nr._signature(data)
    send, why = nr._should_send(
        _DB(_digest(sig, days_ago=nr.DIGEST_REMINDER_DAYS + 1)), data, sig)
    assert send is True and "recordatorio" in why
