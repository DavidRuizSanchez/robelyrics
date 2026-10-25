"""Ritmo y gasto de la ingesta: orden A > B > C, tope semanal y presupuesto de Whisper.

El gasto se deduce de la cola (`via='whisper'` + `duration_s` de lo hecho este
mes), no de un contador: aquí se vigila que la cuenta y el `pending` que ve el
daemon digan lo mismo.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models import YouTubeIngestQueue
from app.routers import ingest
from app.services import corpus_ritmo as ritmo
from app.tests.test_admin_summary import db  # noqa: F401  (fixture SQLite)

AHORA = datetime.now(UTC)


def _fila(db, vid, status="approved", nivel=None, **kw):  # noqa: F811
    r = YouTubeIngestQueue(video_id=vid, url=f"https://youtu.be/{vid}", title=vid,
                           target="corpus", kind="youtube_transcript", status=status,
                           nivel=nivel, **kw)
    db.add(r)
    db.commit()
    return r


def test_pending_va_por_nivel_y_luego_por_antiguedad(db):  # noqa: F811
    _fila(db, "c-viejo", nivel="C", approved_at=AHORA - timedelta(days=5))
    _fila(db, "sin-nivel", approved_at=AHORA - timedelta(days=9))
    _fila(db, "b", nivel="B", approved_at=AHORA - timedelta(days=1))
    _fila(db, "a", nivel="A", approved_at=AHORA)
    assert [p.video_id for p in ingest.list_pending(db)] == ["a", "b", "sin-nivel", "c-viejo"]


def test_tope_semanal(db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ritmo, "MAX_DONE_SEMANA", 3)
    for i in range(2):
        _fila(db, f"hecho{i}", status="done", done_at=AHORA - timedelta(days=2))
    _fila(db, "hace-un-mes", status="done", done_at=AHORA - timedelta(days=30))
    for i in range(4):
        _fila(db, f"p{i}", approved_at=AHORA - timedelta(minutes=i))
    assert len(ingest.list_pending(db)) == 1          # 3 - 2 hechos esta semana
    _fila(db, "hecho3", status="done", done_at=AHORA)
    assert ingest.list_pending(db) == []


def test_presupuesto_de_whisper(db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ritmo, "PRESUPUESTO_MES_USD", 0.6)   # = 100 min
    inicio_mes = AHORA.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    _fila(db, "w", status="done", via="whisper", duration_s=80 * 60,
          done_at=inicio_mes + timedelta(minutes=1))
    _fila(db, "s", status="done", via="subtitulos", duration_s=500 * 60,
          done_at=inicio_mes + timedelta(minutes=2))          # gratis: no cuenta
    _fila(db, "mes-pasado", status="done", via="whisper", duration_s=500 * 60,
          done_at=inicio_mes - timedelta(days=1))
    assert ritmo.gasto_mes_usd(db) == 0.48
    _fila(db, "viejo", status="done", via="whisper", done_at=inicio_mes + timedelta(minutes=3))
    assert ritmo.resumen(db)["whisper_sin_duracion"] == 1   # el gasto es cota inferior
    _fila(db, "cabe", duration_s=15 * 60, approved_at=AHORA)
    _fila(db, "no-cabe", duration_s=30 * 60, approved_at=AHORA + timedelta(seconds=1))
    _fila(db, "sin-duracion", approved_at=AHORA + timedelta(seconds=2))
    ok = {p.video_id: p.whisper_ok for p in ingest.list_pending(db)}
    # Sin duración se supone el peor caso (2 h), que en 20 min no cabe.
    assert ok == {"cabe": True, "no-cabe": False, "sin-duracion": False}
    assert ritmo.whisper_permitido(None, restantes_min=200)


def test_complete_apunta_por_donde_fue_y_cuanto_dura(db, monkeypatch):  # noqa: F811
    from scripts.research import common

    monkeypatch.setattr(common, "upsert_source", lambda db, **kw: 1)
    r = _fila(db, "x", status="processing", duration_s=100.0)
    payload = ingest.CompleteIn.model_validate(
        {"content_clean": "x" * 40, "via": "subtitulos", "duration_s": 912.5})
    ingest.complete(r.id, payload, db)
    assert (r.via, r.duration_s) == ("subtitulos", 912.5)


def test_un_daemon_viejo_cuenta_como_whisper(db, monkeypatch):  # noqa: F811
    from scripts.research import common

    monkeypatch.setattr(common, "upsert_source", lambda db, **kw: 1)
    r = _fila(db, "y", status="processing")
    ingest.complete(r.id, ingest.CompleteIn.model_validate({"content_clean": "x" * 40}), db)
    assert r.via == "whisper"
