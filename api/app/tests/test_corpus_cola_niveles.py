"""La búsqueda del corpus llega a la cola sin perder nada por el camino.

Dos fallos silenciosos que se vigilan aquí:
- un `kind` que la cola admite pero `corpus_for_queries` no sabe atribuir: sus
  pasajes se descartaban sin aviso. La lista de kinds se LEE del CHECK de la BD,
  no se escribe a mano en el test, para que el próximo kind nuevo también caiga.
- el modo sombra: si `CORPUS_AUTO_ENTRY` no está encendido, nada entra solo.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.db.models import YouTubeIngestQueue
from app.services import corpus_for_queries as cfq
from app.services.corpus_trust import Veredicto, Video
from scripts.youtube import detect_uploads


def _kinds_de_la_cola() -> set[str]:
    ck = next(c for c in YouTubeIngestQueue.__table__.constraints
              if getattr(c, "name", "") == "ck_youtube_ingest_kind")
    return set(re.findall(r"'([a-z_]+)'", str(ck.sqltext)))


def test_todo_kind_de_la_cola_se_puede_atribuir():
    kinds = _kinds_de_la_cola()
    assert {"entorno_interview", "media_report"} <= kinds
    for kind in kinds:
        assert cfq.atribucion({"kind": kind, "author": "Alguien"}), kind


def test_el_testimonio_del_entorno_se_afirma_sin_citar():
    bloque = cfq.bloque_material([
        {"kind": "entorno_interview", "fragmento": "Grabamos Agila en Iruña.", "consulta": "agila"},
        {"kind": "media_report", "fragmento": "El reportaje dice…", "consulta": "agila"},
    ])
    entorno, fondo = bloque.split("====")[0], bloque.split("====")[-1]
    assert "TESTIMONIOS DEL ENTORNO" in entorno and "Grabamos Agila" in entorno
    assert "PROHIBIDO nombrar" in entorno
    assert fondo.lstrip().startswith("FONDO") and "El reportaje" in fondo


def test_en_un_dossier_el_reportaje_es_fondo_y_el_entorno_propio():
    propio, fondo = cfq.separar_material(
        "[entorno_interview · Uoho en RockFM]\nGrabamos Agila…\n\n----\n\n"
        "[media_report · Especial RTVE]\nEl especial cuenta…")
    assert "Uoho en RockFM" in propio and "Especial RTVE" in fondo


def _resultado(nivel, kind, vid):
    video = Video(video_id=vid, title=f"vídeo {vid}", channel_title="RockFM",
                  channel_id="UC1", duration_s=900.0)
    return video, Veredicto(nivel, kind, ["robe-iniesta"], ["motivo"]), {
        "consulta": "q", "published_at": "2024-05-01T10:00:00Z"}


@pytest.fixture
def busqueda(monkeypatch):
    from contextlib import contextmanager

    from scripts.youtube import corpus_search

    resultados = [
        _resultado("A", "robe_interview", "a1"),
        _resultado("B", "media_report", "b1"),
        _resultado("C", "youtube_transcript", "c1"),
        _resultado("descartado", None, "d1"),
    ]
    monkeypatch.setattr(corpus_search, "descubrir", lambda db, key, **kw: resultados)

    @contextmanager
    def sesion():
        yield None

    monkeypatch.setattr(detect_uploads, "get_session", sesion)

    def ajustes(auto):
        monkeypatch.setattr(detect_uploads, "get_settings", lambda: SimpleNamespace(
            youtube_api_key="k", corpus_auto_entry=auto))
    return ajustes


def test_en_modo_sombra_nada_entra_solo(busqueda):
    busqueda(False)
    filas = {f["video_id"]: f for f in detect_uploads._search_candidates(False, set())}
    assert set(filas) == {"a1", "b1", "c1"}
    assert {f["status"] for f in filas.values()} == {"detected"}
    assert filas["a1"]["target"] == "robe_voice" and filas["b1"]["target"] == "corpus"
    assert filas["a1"]["nivel"] == "A" and filas["a1"]["descubierto_por"] == "busqueda"


def test_con_la_entrada_automatica_solo_a_y_b_entran_solos(busqueda):
    busqueda(True)
    filas = {f["video_id"]: f for f in detect_uploads._search_candidates(False, set())}
    assert filas["a1"]["status"] == filas["b1"]["status"] == "approved"
    assert filas["c1"]["status"] == "detected"


def test_el_historico_no_encola_los_de_fan(busqueda):
    busqueda(False)
    filas = detect_uploads._search_candidates(True, set())
    assert {f["video_id"] for f in filas} == {"a1", "b1"}


def test_las_filas_casan_con_el_modelo(busqueda):
    busqueda(False)
    for f in detect_uploads._search_candidates(False, set()):
        YouTubeIngestQueue(**{k: v for k, v in f.items() if k != "reasons"})


def test_el_correo_no_aprueba_en_lote(monkeypatch):
    """25-10-2026: un «aprobar e ingerir» del lote entero metió trece vídeos de
    spam junto a dos buenos. Cada enlace aprueba UN vídeo, y lo ya aprobado no
    lleva enlace."""
    from app.services import email as email_mod
    from app.services.auth import decode_youtube_ingest_token

    enviados = []
    monkeypatch.setenv("ADMIN_EMAIL", "admin@x.tld")
    monkeypatch.setattr(email_mod, "send_email", lambda **kw: enviados.append(kw))
    filas = [YouTubeIngestQueue(id=i, video_id=f"v{i}", url=f"https://youtu.be/v{i}",
                                title=f"vídeo {i}", target="corpus", kind="youtube_transcript",
                                nivel=n, status=st)
             for i, n, st in [(1, "C", "detected"), (2, "C", "detected"), (3, "A", "approved")]]
    detect_uploads._send_email(filas)

    html = enviados[0]["html"]
    tokens = re.findall(r"youtube-ingest\?token=([\w.-]+)", html)
    assert len(tokens) == 2
    assert sorted(decode_youtube_ingest_token(t)["queue_ids"] for t in tokens) == [[1], [2]]
    assert "/biblioteca/admin/corpus" in html
