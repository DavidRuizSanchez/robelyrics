"""Correo semanal del corpus y «Retirar» desde el correo.

Lo que se blinda: que la sequía avise aunque no haya nada nuevo (el fallo
silencioso del 29-07 al 23-10-2026), que la misma semana no mande dos correos, y
que el enlace de retirar NO borre al abrirlo: los escáneres de enlaces de los
correos abren las URLs solos.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models import InterpretationSource, NotificationDigest, YouTubeIngestQueue
from app.routers import public
from app.services.auth import create_corpus_retire_token, create_youtube_ingest_token
from app.tests.test_admin_summary import db  # noqa: F401  (fixture SQLite)
from app.tests.test_corpus_queue import _QdrantFalso
from scripts import notify_corpus as nc

AHORA = datetime.now(UTC)


def _fila(db, vid, status="done", **kw):  # noqa: F811
    r = YouTubeIngestQueue(video_id=vid, url=f"https://youtu.be/{vid}", title=f"Vídeo {vid}",
                           target="corpus", kind="youtube_transcript", status=status, **kw)
    db.add(r)
    db.commit()
    return r


def test_la_sequia_avisa_aunque_no_haya_nada_nuevo(db):  # noqa: F811
    data = nc._gather(db, AHORA)
    assert nc.sequia(data)
    assert nc._should_send(db, data, nc._signature(data)) == (True, "primer correo")


def test_con_fuentes_nuevas_no_hay_sequia(db):  # noqa: F811
    db.add(InterpretationSource(kind="blog", url="https://b.test/1", fetched_at=AHORA))
    db.commit()
    assert not nc.sequia(nc._gather(db, AHORA))


def test_la_misma_semana_no_manda_dos_correos(db):  # noqa: F811
    _fila(db, "a", done_at=AHORA - timedelta(days=1), nivel="A")
    db.add(InterpretationSource(kind="robe_interview", url="https://youtu.be/a",
                                fetched_at=AHORA))
    db.commit()
    data = nc._gather(db, AHORA)
    firma = nc._signature(data)
    db.add(NotificationDigest(kind=nc._KIND, signature=firma, sent_at=AHORA))
    db.commit()
    assert nc._should_send(db, data, firma) == (False, "lo mismo que el último correo")
    _fila(db, "b", status="detected", created_at=AHORA)
    data = nc._gather(db, AHORA)
    assert nc._should_send(db, data, nc._signature(data))[0]


def test_el_correo_lleva_retirar_y_aprobar_de_uno_en_uno(db):  # noqa: F811
    _fila(db, "a", done_at=AHORA - timedelta(days=1), nivel="A",
          motivos=["voz: Robe", "juez tras transcribir (Robe): no pasa", "baja de A a B"])
    _fila(db, "c", status="detected", nivel="C", created_at=AHORA - timedelta(days=9))
    data = nc._gather(db, AHORA)
    cuerpo = nc._build_html(data, "https://x.test")
    assert cuerpo.count("corpus-retire?token=") == 1
    assert cuerpo.count("youtube-ingest?token=") == 1
    assert "más de 7 días" in cuerpo and "bajaron de A a fondo" in cuerpo


def test_abrir_el_enlace_de_retirar_no_borra(db):  # noqa: F811
    r = _fila(db, "x", done_at=AHORA)
    resp = public.corpus_retire_confirm(create_corpus_retire_token(r.id), db)
    assert resp.status_code == 200 and b"method=\"post\"" in resp.body
    assert db.get(YouTubeIngestQueue, r.id).status == "done"


def test_el_post_retira_y_es_idempotente(db, monkeypatch):  # noqa: F811
    from app.services import qdrant_client

    monkeypatch.setattr(qdrant_client, "get_qdrant", lambda: _QdrantFalso())
    r = _fila(db, "y", done_at=AHORA)
    token = create_corpus_retire_token(r.id)
    assert "Retirado" in public.corpus_retire(token, db).body.decode()
    assert db.get(YouTubeIngestQueue, r.id).status == "retired"
    assert "Ya estaba retirado" in public.corpus_retire(token, db).body.decode()


def test_un_token_de_aprobar_no_retira(db):  # noqa: F811
    r = _fila(db, "z", done_at=AHORA)
    resp = public.corpus_retire(create_youtube_ingest_token([r.id]), db)
    assert resp.status_code == 400
    assert db.get(YouTubeIngestQueue, r.id).status == "done"


def test_abrir_el_enlace_de_aprobar_no_aprueba(db):  # noqa: F811
    """Un escáner de enlaces que abre el correo no puede poner a pagar Whisper."""
    r = _fila(db, "a", status="detected")
    resp = public.youtube_ingest_confirm(create_youtube_ingest_token([r.id]), db)
    assert resp.status_code == 200 and b"method=\"post\"" in resp.body
    assert "Vídeo a" in resp.body.decode()
    assert db.get(YouTubeIngestQueue, r.id).status == "detected"


def test_el_post_aprueba_y_es_idempotente(db):  # noqa: F811
    r = _fila(db, "b", status="detected")
    token = create_youtube_ingest_token([r.id])
    assert "Aprobados 1" in public.youtube_ingest_approve(token, db).body.decode()
    assert db.get(YouTubeIngestQueue, r.id).status == "approved"
    assert "Aprobados 0" in public.youtube_ingest_approve(token, db).body.decode()


def test_un_token_de_retirar_no_aprueba(db):  # noqa: F811
    r = _fila(db, "c", status="detected")
    assert public.youtube_ingest_confirm(create_corpus_retire_token(r.id), db).status_code == 400
    assert public.youtube_ingest_approve(create_corpus_retire_token(r.id), db).status_code == 400
    assert db.get(YouTubeIngestQueue, r.id).status == "detected"
