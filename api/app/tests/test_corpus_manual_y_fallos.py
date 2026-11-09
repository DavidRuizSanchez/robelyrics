"""Corpus a mano y fallos que no se arreglan reintentando (09-11-2026).

- Un vídeo de Juancares estrenado ocho horas después de la pasada de
  `detect_uploads` esperaba tres días, un clic y su hueco semanal. Añadirlo a
  mano ya es la decisión: entra aprobado, el primero y sin gastar hueco.
- Restricción de edad, vídeo casi sin habla: agotaban sus 3 intentos y se
  quedaban en «Fallidos» para siempre. Ahora `abandoned`, con motivo.
- El extractor roto (iVoox) NO es permanente: lo arregla actualizar yt-dlp.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models import InterpretationSource, YouTubeIngestQueue
from app.routers import ingest
from app.services import corpus_fallos, corpus_manual, corpus_queue
from app.services import corpus_ritmo as ritmo
from app.tests.test_admin_summary import db  # noqa: F401  (fixture SQLite)

AHORA = datetime.now(UTC)
JUANCARES = "https://www.youtube.com/watch?v=cwUsXq54KvA"
DETALLES = {"cwUsXq54KvA": {
    "title": "¡ESTRENO! PLASENCIA Y ROBE. CAPÍTULO 64", "channel_title": "Juancaraes",
    "channel_id": "UCx", "published_at": "2026-11-07T15:00:00Z", "duration_s": 12540.0}}


def _detalles(vid):
    return DETALLES.get(vid, {})


def _fila(db, vid, status="approved", **kw):  # noqa: F811
    r = YouTubeIngestQueue(video_id=vid, url=f"https://youtu.be/{vid}", title=vid,
                           target="corpus", kind="youtube_transcript", status=status, **kw)
    db.add(r)
    db.commit()
    return r


# --------------------------------------------------------------------------- #
# Alta manual
# --------------------------------------------------------------------------- #
def test_un_video_de_youtube_entra_con_su_id_real_y_aprobado(db):  # noqa: F811
    r = corpus_manual.anadir(db, "https://youtu.be/cwUsXq54KvA", "youtube_transcript",
                             detalles=_detalles)
    fila = db.get(YouTubeIngestQueue, r["id"])
    assert r["estado"] == "nuevo"
    assert fila.video_id == "cwUsXq54KvA" and fila.url == JUANCARES
    assert fila.status == "approved" and fila.descubierto_por == "manual"
    assert fila.title.startswith("¡ESTRENO!") and fila.duration_s == 12540.0
    assert fila.target == "corpus" and fila.nivel == "C"


def test_habla_robe_va_a_la_voz(db):  # noqa: F811
    r = corpus_manual.anadir(db, JUANCARES, "robe_interview", detalles=_detalles)
    assert db.get(YouTubeIngestQueue, r["id"]).target == "robe_voice"


def test_repetida_no_se_duplica(db):  # noqa: F811
    corpus_manual.anadir(db, JUANCARES, "youtube_transcript", detalles=_detalles)
    r = corpus_manual.anadir(db, "https://youtu.be/cwUsXq54KvA", "youtube_transcript",
                             detalles=_detalles)
    assert db.query(YouTubeIngestQueue).count() == 1
    assert r["estado"] == "priorizado"


def test_si_estaba_detectada_pasa_a_aprobada_y_la_primera(db):  # noqa: F811
    _fila(db, "cwUsXq54KvA", status="detected", descubierto_por="canal")
    r = corpus_manual.anadir(db, JUANCARES, "youtube_transcript", detalles=_detalles)
    fila = db.get(YouTubeIngestQueue, r["id"])
    assert fila.status == "approved" and fila.descubierto_por == "manual"
    assert any("encontrado por canal" in m for m in fila.motivos)


def test_lo_ya_ingerido_se_dice_y_no_se_toca(db):  # noqa: F811
    db.add(InterpretationSource(kind="youtube_transcript", url=JUANCARES, title="x"))
    db.commit()
    r = corpus_manual.anadir(db, JUANCARES, "youtube_transcript", detalles=_detalles)
    assert r["estado"] == "ya_estaba"
    assert db.query(YouTubeIngestQueue).count() == 0


def test_un_audio_suelto_usa_la_clave_de_enqueue_audio(db):  # noqa: F811
    from scripts.youtube import enqueue_audio

    url = "https://www.ivoox.com/x_rf_1_1.html"
    with pytest.raises(corpus_manual.ManualError):
        corpus_manual.anadir(db, url, "media_report")           # sin título
    r = corpus_manual.anadir(db, url, "media_report", titulo="La Gran Travesía")
    assert db.get(YouTubeIngestQueue, r["id"]).video_id == enqueue_audio.clave(url)


def test_un_video_que_youtube_no_devuelve_pide_titulo(db):  # noqa: F811
    with pytest.raises(corpus_manual.ManualError, match="privado o borrado"):
        corpus_manual.anadir(db, "https://youtu.be/nonexistent1", "media_report",
                             detalles=_detalles)


def test_lo_manual_va_primero_y_no_gasta_hueco(db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ritmo, "MAX_DONE_SEMANA", 2)
    _fila(db, "a", nivel="A", approved_at=AHORA - timedelta(days=3))
    _fila(db, "b", nivel="B", approved_at=AHORA - timedelta(days=2))
    _fila(db, "manual", nivel="C", approved_at=AHORA, descubierto_por="manual")
    assert [p.video_id for p in ingest.list_pending(db)] == ["manual", "a", "b"]
    # Hecho lo manual, el tope sigue entero para la búsqueda.
    _fila(db, "manual-hecho", status="done", done_at=AHORA, descubierto_por="manual")
    assert ritmo.hechos_semana(db) == 0
    # Y con el tope agotado, lo manual sigue saliendo.
    for i in range(2):
        _fila(db, f"hecho{i}", status="done", done_at=AHORA)
    assert [p.video_id for p in ingest.list_pending(db)] == ["manual"]


# --------------------------------------------------------------------------- #
# Fallos: permanente, extractor, transitorio
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("error,clase", [
    ("RuntimeError: yt-dlp: ERROR: [youtube] x: Sign in to confirm your age.", "permanente"),
    ("RuntimeError: transcripción demasiado corta (51 chars < 72 para 36s de audio)",
     "permanente"),
    ("RuntimeError: yt-dlp: ERROR: [youtube] x: Private video. Sign in", "permanente"),
    ("RuntimeError: yt-dlp: ERROR: [youtube] x: Video unavailable", "permanente"),
    ("RuntimeError: yt-dlp: ERROR: expected string or bytes-like object, got 'bool'",
     "extractor"),
    ("HTTPStatusError: Server error '502 Bad Gateway' for url …/claim", "transitorio"),
    ("ConnectError: [Errno 8] nodename nor servname provided", "transitorio"),
    ("algo que nadie ha visto nunca", "transitorio"),
])
def test_clasificar(error, clase):
    assert corpus_fallos.clasificar(error) == clase


def _fallar(db, fila, error, version="2026.8.19"):  # noqa: F811
    return ingest.fail(fila.id, ingest.FailIn(error=error, ytdlp_version=version), db)


def test_un_permanente_en_el_ultimo_intento_queda_abandonado(db):  # noqa: F811
    fila = _fila(db, "rockfm", attempts=ingest.MAX_ATTEMPTS - 1)
    out = _fallar(db, fila, "RuntimeError: yt-dlp: ERROR: Sign in to confirm your age")
    assert out.status == "abandoned"
    assert corpus_queue._fila(fila)["motivo_abandono"].startswith("YouTube pide confirmar")


def test_un_permanente_antes_del_ultimo_intento_sigue_fallido(db):  # noqa: F811
    fila = _fila(db, "rockfm")
    assert _fallar(db, fila, "Sign in to confirm your age").status == "failed"


def test_un_502_en_el_ultimo_intento_no_abandona(db):  # noqa: F811
    fila = _fila(db, "rebuild", attempts=ingest.MAX_ATTEMPTS - 1)
    out = _fallar(db, fila, "HTTPStatusError: Server error '502 Bad Gateway'")
    assert out.status == "failed" and fila.attempts == ingest.MAX_ATTEMPTS


def test_un_extractor_roto_no_gasta_intento_y_espera_otra_version(db):  # noqa: F811
    fila = _fila(db, "audio:ivoox", attempts=1)
    _fallar(db, fila, "RuntimeError: yt-dlp: ERROR: expected string or bytes-like object")
    assert fila.status == "failed" and fila.attempts == 1
    assert fila.error.startswith("[extractor · yt-dlp 2026.8.19]")
    assert ingest.list_pending(db, ytdlp="2026.8.19") == []
    assert [p.video_id for p in ingest.list_pending(db, ytdlp="2026.10.26")] == ["audio:ivoox"]


def test_un_daemon_viejo_sin_version_gasta_intento_como_siempre(db):  # noqa: F811
    fila = _fila(db, "audio:ivoox")
    _fallar(db, fila, "RuntimeError: yt-dlp: ERROR: expected string or bytes-like object",
            version=None)
    assert fila.attempts == 1 and not fila.error.startswith("[extractor")


def test_un_fallo_sin_error_previo_no_se_cuela_fuera_de_pending(db):  # noqa: F811
    """`error` NULL: sin `coalesce`, el NOT de NULL dejaba la fila fuera."""
    _fila(db, "nuevo")
    assert [p.video_id for p in ingest.list_pending(db, ytdlp="2026.8.19")] == ["nuevo"]


def test_lo_abandonado_se_puede_reintentar_y_descartar(db):  # noqa: F811
    fila = _fila(db, "x", status="abandoned", attempts=3, error="Sign in to confirm your age")
    assert corpus_queue.decidir(db, fila.id, "reintentar")["status"] == "approved"
    assert fila.attempts == 0 and fila.error is None
    fila.status = "abandoned"
    db.commit()
    assert corpus_queue.decidir(db, fila.id, "descartar")["status"] == "retired"


def test_el_panel_cuenta_lo_abandonado_y_avisa_del_presupuesto(db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ritmo, "PRESUPUESTO_MES_USD", 0.06)   # = 10 min
    _fila(db, "ab", status="abandoned", error="Private video")
    _fila(db, "largo", duration_s=3600, approved_at=AHORA)
    out = corpus_queue.listar(db)
    assert out["cuenta"]["abandoned"] == 1
    assert out["filas"]["abandoned"][0]["motivo_abandono"] == "el vídeo es privado"
    assert out["filas"]["approved"][0]["whisper_ok"] is False


def test_download_audio_sube_el_motivo_de_yt_dlp(monkeypatch, tmp_path):
    """Con `check=True` a prod solo llegaba «returned non-zero exit status 1»."""
    import subprocess

    from scripts.research import transcribe_juancares as tj

    def _run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, "", "ERROR: [youtube] x: Sign in to "
                                                      "confirm your age\n")

    monkeypatch.setattr(tj.subprocess, "run", _run)
    with pytest.raises(RuntimeError, match="confirm your age"):
        tj.download_audio("x", str(tmp_path))
    assert corpus_fallos.clasificar("RuntimeError: yt-dlp: ERROR: [youtube] x: Sign in to "
                                    "confirm your age") == "permanente"
