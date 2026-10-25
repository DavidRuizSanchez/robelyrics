"""Daemon de ingesta de YouTube ↔ endpoint `complete`.

Desde el 23-09-2026 `transcribe()` devuelve `(texto, tramos)` y el daemon lo
seguía tratando como texto: `clean_text` recibía la tupla y el primer vídeo
aprobado habría acabado en `failed` tras tres intentos. Nadie lo vio porque no
había ni un test del daemon.

Por eso aquí NO se mockea `transcribe`: corre la de verdad contra un cliente de
OpenAI falso que responde con la forma de `verbose_json`. Un mock de
`transcribe` que devolviera texto habría dado verde con el bug dentro.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.routers import ingest
from scripts.research import transcribe_juancares
from scripts.youtube import process_queue

BASE = "https://prod.test/api"


class _FakeWhisper:
    """Responde como `audio.transcriptions.create(response_format="verbose_json")`."""

    def __init__(self):
        self.audio = SimpleNamespace(transcriptions=self)

    def create(self, **_):
        return SimpleNamespace(
            text="Esto lo escribí en Plasencia, en una noche muy larga",
            segments=[
                SimpleNamespace(start=0.0, end=4.2, text="Esto lo escribí en Plasencia,",
                                no_speech_prob=0.01, avg_logprob=-0.2),
                SimpleNamespace(start=4.2, end=7.9, text="en una noche muy larga",
                                no_speech_prob=0.02, avg_logprob=-0.3),
            ],
        )


@pytest.fixture
def audio_falso(monkeypatch, tmp_path):
    trozos = []
    for i in range(2):
        p = tmp_path / f"chunk_{i}.mp3"
        p.write_bytes(b"\x00")
        trozos.append(str(p))
    monkeypatch.setattr(process_queue, "download_audio",
                        lambda vid, td, url=None: str(tmp_path / "a.mp3"))
    monkeypatch.setattr(process_queue, "audio_duration_s", lambda path: 2500.0)
    monkeypatch.setattr(process_queue, "split_audio", lambda path, td: trozos)
    # Sin subtítulos: estos tests son del camino de Whisper, y sin esto saldrían a YouTube.
    monkeypatch.setattr(process_queue, "fetch_subtitles", lambda vid: None)
    return trozos


def _cliente(llamadas: list[tuple[str, dict | None]], claim_status: int = 200):
    def responder(request: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(request.content) if request.content else None
        llamadas.append((request.url.path, cuerpo))
        if request.url.path.endswith("/claim"):
            return httpx.Response(claim_status, json={"detail": "ya reclamado"})
        return httpx.Response(200, json={"status": "done"})

    return httpx.Client(transport=httpx.MockTransport(responder))


def test_el_daemon_manda_texto_y_tramos_absolutos(audio_falso):
    llamadas: list = []
    item = {"id": 50, "video_id": "abc123", "title": "TEASER 1"}
    with _cliente(llamadas) as http:
        assert process_queue._procesar(http, BASE, _FakeWhisper(), item) is True

    ruta, cuerpo = llamadas[-1]
    assert ruta.endswith("/ingest/youtube/50/complete")
    assert isinstance(cuerpo["content_clean"], str)
    assert "Plasencia" in cuerpo["content_clean"]
    tramos = cuerpo["segments"]
    assert len(tramos) == 4
    # El segundo trozo empieza CHUNK_SECONDS más tarde: sin el offset mentiría.
    assert tramos[2]["start_s"] == transcribe_juancares.CHUNK_SECONDS
    # Lo que manda el daemon lo acepta el endpoint tal cual.
    ingest.CompleteIn.model_validate(cuerpo)


def test_un_409_en_el_claim_no_transcribe(audio_falso):
    llamadas: list = []
    item = {"id": 50, "video_id": "abc123", "title": "TEASER 1"}
    with _cliente(llamadas, claim_status=409) as http:
        assert process_queue._procesar(http, BASE, _FakeWhisper(), item) is False
    assert [r for r, _ in llamadas] == ["/api/ingest/youtube/50/claim"]


def test_complete_acepta_un_daemon_viejo_sin_tramos():
    payload = ingest.CompleteIn.model_validate({"content_clean": "x" * 40, "title": "t"})
    assert payload.segments is None


class _FakeDB:
    def __init__(self, row):
        self.row, self.commits = row, 0

    def get(self, _model, _id):
        return self.row

    def commit(self):
        self.commits += 1


def _fila():
    return SimpleNamespace(kind="robe_interview", url="https://youtu.be/abc123", title="T",
                           author=None, published_at=None, status="processing",
                           error=None, done_at=None)


def test_complete_guarda_los_tramos_en_la_fuente(monkeypatch):
    from scripts.research import common

    guardados: dict = {}
    monkeypatch.setattr(common, "upsert_source", lambda db, **kw: 782)
    monkeypatch.setattr(common, "guardar_segmentos",
                        lambda db, sid, segs: guardados.update(sid=sid, segs=segs) or len(segs))
    db = _FakeDB(_fila())
    payload = ingest.CompleteIn.model_validate({
        "content_clean": "x" * 40,
        "segments": [{"start_s": 1200.0, "end_s": 1204.2, "text": "hola"}],
    })
    assert ingest.complete(50, payload, db).status == "done"
    assert guardados["sid"] == 782
    assert guardados["segs"][0]["start_s"] == 1200.0


def test_complete_sin_tramos_no_borra_los_que_hubiera(monkeypatch):
    from scripts.research import common

    monkeypatch.setattr(common, "upsert_source", lambda db, **kw: 782)

    def no_llamar(*_):
        raise AssertionError("sin tramos no se reemplaza nada")

    monkeypatch.setattr(common, "guardar_segmentos", no_llamar)
    db = _FakeDB(_fila())
    payload = ingest.CompleteIn.model_validate({"content_clean": "x" * 40})
    assert ingest.complete(50, payload, db).status == "done"
    assert db.commits == 1


# --- Fase 3: subtítulos gratis primero, Whisper con presupuesto -------------

_SUBS = ([{"start_s": 0.0, "end_s": 3.0, "text": "Robe: esto lo grabamos"},
          {"start_s": 3.0, "end_s": 900.0,
           "text": "en Iruña con mucho frío, y aquella semana no paramos de tocar " * 3}], False)


@pytest.mark.parametrize("item,subs,via", [
    ({"nivel": "C"}, _SUBS, "subtitulos"),
    ({"nivel": "A", "duration_s": 900.0}, (_SUBS[0], True), "whisper"),     # A, automáticos, corto
    ({"nivel": "A", "duration_s": 900.0}, _SUBS, "subtitulos"),             # A con subtítulos manuales
    ({"nivel": "A", "duration_s": 3600.0}, (_SUBS[0], True), "subtitulos"),  # A largo
    ({"nivel": "A", "duration_s": 900.0, "whisper_ok": False}, (_SUBS[0], True), "subtitulos"),
    ({"nivel": "B"}, None, "whisper"),
    ({"nivel": "B", "whisper_ok": False}, None, None),                      # no cabe: espera
])
def test_elegir_via(item, subs, via):
    assert process_queue.elegir_via(item, subs) == via


def test_con_subtitulos_no_se_descarga_ni_se_paga(monkeypatch):
    def no_llamar(*_):
        raise AssertionError("con subtítulos no se baja audio")

    monkeypatch.setattr(process_queue, "fetch_subtitles", lambda vid: _SUBS)
    monkeypatch.setattr(process_queue, "download_audio", no_llamar)
    llamadas: list = []
    with _cliente(llamadas) as http:
        assert process_queue._procesar(http, BASE, None, {"id": 7, "video_id": "s1",
                                                          "nivel": "C"}) is True
    _, cuerpo = llamadas[-1]
    assert cuerpo["via"] == "subtitulos" and cuerpo["duration_s"] == 900.0
    assert cuerpo["segments"][1]["start_s"] == 3.0
    ingest.CompleteIn.model_validate(cuerpo)


def test_sin_subtitulos_ni_presupuesto_ni_se_reclama(monkeypatch):
    monkeypatch.setattr(process_queue, "fetch_subtitles", lambda vid: None)
    llamadas: list = []
    with _cliente(llamadas) as http:
        assert process_queue._procesar(http, BASE, None, {"id": 8, "video_id": "s2",
                                                          "whisper_ok": False}) is False
    assert llamadas == []   # sin claim: no queda en `processing` ni gasta intento


def test_un_audio_de_ivoox_se_baja_por_su_url_y_sin_subtitulos(monkeypatch, tmp_path):
    from scripts.youtube.enqueue_audio import clave

    url = "https://www.ivoox.com/extremoduro-robe-especial_rf_164164848_1.html"
    pedido = {}

    def no_subtitulos(_):
        raise AssertionError("un audio de iVoox no tiene subtítulos de YouTube")

    monkeypatch.setattr(process_queue, "fetch_subtitles", no_subtitulos)
    monkeypatch.setattr(process_queue, "download_audio",
                        lambda vid, td, url=None: pedido.update(url=url) or str(tmp_path / "a"))
    monkeypatch.setattr(process_queue, "audio_duration_s", lambda path: 3470.0)
    trozos = []
    for i in range(2):
        (tmp_path / f"c{i}").write_bytes(b"\x00")
        trozos.append(str(tmp_path / f"c{i}"))
    monkeypatch.setattr(process_queue, "split_audio", lambda path, td: trozos)
    llamadas: list = []
    item = {"id": 9, "video_id": clave(url), "url": url, "title": "Especial 2ª parte"}
    with _cliente(llamadas) as http:
        assert process_queue._procesar(http, BASE, _FakeWhisper(), item) is True
    assert pedido["url"] == url
    assert llamadas[-1][1]["via"] == "whisper" and len(clave(url)) <= 32


@pytest.mark.parametrize("url,yt", [
    ("https://www.youtube.com/watch?v=abc", True), ("https://youtu.be/abc", True),
    ("", True), ("https://www.ivoox.com/x.html", False),
])
def test_es_youtube(url, yt):
    assert process_queue.es_youtube({"url": url}) is yt
