"""Tests del camino de recuperación por TEXTO sobre interpretations_v1.

Lo que se blinda es lo que hacía falta arreglar: que una fuente SIN canción
asociada se pueda recuperar (antes su hit se descartaba, porque la única lectura
de la colección devolvía `payload.song_ids`), y que el pasaje se rehidrate bien
desde la BD aunque Qdrant no guarde el texto.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import ARRAY, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.db.models import InterpretationSource
from app.services import retrieval


# `interpretation_sources.referenced_song_ids` es un ARRAY de Postgres y SQLite no
# sabe renderizarlo, así que la tabla no se puede crear en memoria. La columna no
# interviene en lo que se prueba aquí (la gracia del camino semántico es justamente
# no depender de ella): basta con que el dialecto de test sepa emitir algo.
@compiles(ARRAY, "sqlite")
def _array_como_json_en_sqlite(element, compiler, **kw):  # noqa: ARG001
    return "JSON"


@dataclass
class _Point:
    payload: dict
    score: float = 0.5


class _Resp:
    def __init__(self, points):
        self.points = points


class _FakeQdrant:
    def __init__(self, points, boom=False):
        self._points = points
        self._boom = boom
        self.last_kwargs = None

    def query_points(self, **kw):
        if self._boom:
            raise RuntimeError("qdrant caído")
        self.last_kwargs = kw
        return _Resp(self._points)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    InterpretationSource.__table__.create(engine)
    with Session(engine) as s:
        yield s


def _src(db, *, kind="youtube_transcript", content="x", refs=None, title="T"):
    row = InterpretationSource(
        kind=kind, url=f"https://y.tld/{title}", title=title, author="Juancares",
        content_raw=content, content_clean=content, referenced_song_ids=refs,
        for_seo_only=False,
    )
    db.add(row)
    db.flush()
    return row


def _patch(monkeypatch, points, boom=False):
    fake = _FakeQdrant(points, boom=boom)
    monkeypatch.setattr(retrieval, "get_qdrant", lambda: fake)
    return fake


def test_recupera_fuente_sin_cancion(db, monkeypatch):
    """El caso que motivó todo: sin song_ids y aun así debe salir."""
    src = _src(db, content="Un análisis largo del disco. " * 20, refs=None)
    _patch(monkeypatch, [_Point({
        "source_id": src.id, "chunk_index": 0, "kind": src.kind,
        "title": src.title, "author": src.author, "url": src.url, "song_ids": [],
    })])
    out = retrieval.search_interpretations_passages(db, [0.1] * 8)
    assert len(out) == 1
    assert out[0]["source_id"] == src.id
    assert "análisis largo" in out[0]["fragmento"]


def test_devuelve_el_chunk_indicado(db, monkeypatch):
    """El texto se rehidrata troceando igual que al indexar: chunk_index manda."""
    from scripts.research.embed_interpretations import chunk_text

    largo = " ".join(f"frase numero {i} con relleno suficiente." for i in range(400))
    src = _src(db, content=largo)
    trozos = chunk_text(largo)
    assert len(trozos) > 1, "el fixture necesita más de un chunk para tener sentido"

    _patch(monkeypatch, [_Point({
        "source_id": src.id, "chunk_index": 1, "kind": src.kind,
        "title": src.title, "url": src.url,
    })])
    out = retrieval.search_interpretations_passages(db, [0.1] * 8)
    assert out[0]["fragmento"].startswith(trozos[1].strip()[:40])


def test_chunk_index_fuera_de_rango_cae_al_primero(db, monkeypatch):
    """Si el contenido cambió tras el embed, no se revienta: se sirve el primero."""
    src = _src(db, content="Contenido corto pero suficiente para el test. " * 5)
    _patch(monkeypatch, [_Point({
        "source_id": src.id, "chunk_index": 99, "kind": src.kind, "title": src.title,
    })])
    out = retrieval.search_interpretations_passages(db, [0.1] * 8)
    assert len(out) == 1
    assert out[0]["fragmento"].startswith("Contenido corto")


def test_un_pasaje_por_fuente(db, monkeypatch):
    src = _src(db, content="Material repetido de la misma fuente. " * 30)
    puntos = [
        _Point({"source_id": src.id, "chunk_index": i, "kind": src.kind, "title": src.title},
               score=0.9 - i / 10)
        for i in range(4)
    ]
    _patch(monkeypatch, puntos)
    out = retrieval.search_interpretations_passages(db, [0.1] * 8)
    assert len(out) == 1, "no se puede inundar el prompt con la misma fuente"


def test_excluye_kinds_pedidos(db, monkeypatch):
    """Los comentarios de YouTube son ruido corto: fuera por defecto."""
    com = _src(db, kind="youtube_comment", content="Grande Robe, siempre. " * 10, title="C")
    tra = _src(db, kind="youtube_transcript", content="Analicemos el disco. " * 20, title="A")
    _patch(monkeypatch, [
        _Point({"source_id": com.id, "chunk_index": 0, "kind": "youtube_comment", "title": "C"}),
        _Point({"source_id": tra.id, "chunk_index": 0, "kind": "youtube_transcript", "title": "A"}),
    ])
    out = retrieval.search_interpretations_passages(db, [0.1] * 8)
    assert [o["kind"] for o in out] == ["youtube_transcript"]


def test_fuente_sin_contenido_no_se_devuelve(db, monkeypatch):
    src = _src(db, content="")
    _patch(monkeypatch, [_Point({
        "source_id": src.id, "chunk_index": 0, "kind": src.kind, "title": src.title,
    })])
    assert retrieval.search_interpretations_passages(db, [0.1] * 8) == []


def test_qdrant_caido_no_rompe_la_generacion(db, monkeypatch):
    _patch(monkeypatch, [], boom=True)
    assert retrieval.search_interpretations_passages(db, [0.1] * 8) == []


def test_payload_sin_source_id_se_ignora(db, monkeypatch):
    _patch(monkeypatch, [_Point({"chunk_index": 0, "kind": "forum"})])
    assert retrieval.search_interpretations_passages(db, [0.1] * 8) == []


def test_respeta_el_tope_de_caracteres(db, monkeypatch):
    src = _src(db, content="palabra " * 5000)
    _patch(monkeypatch, [_Point({
        "source_id": src.id, "chunk_index": 0, "kind": src.kind, "title": src.title,
    })])
    out = retrieval.search_interpretations_passages(db, [0.1] * 8, max_chars=300)
    assert len(out[0]["fragmento"]) <= 300
