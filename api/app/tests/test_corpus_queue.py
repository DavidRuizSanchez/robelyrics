"""La cola de ingesta se decide desde el panel con las mismas reglas que el correo.

Hasta el 24-10-2026 solo se aprobaba con el botón del correo; si se perdía, el
vídeo se quedaba en `detected` para siempre (el teaser #50 esperó 11 días).
"""
from __future__ import annotations

import pytest

from app.db.models import YouTubeIngestQueue
from app.services.corpus_queue import AccionNoValida, decidir, listar
from app.tests.test_admin_summary import db  # noqa: F401  (fixture SQLite)


def _video(db, vid, status="detected", nivel=None, **kw):  # noqa: F811
    r = YouTubeIngestQueue(video_id=vid, url=f"https://youtu.be/{vid}", title=vid,
                           target="corpus", kind="youtube_transcript", status=status,
                           nivel=nivel, **kw)
    db.add(r)
    db.commit()
    return r


def test_aprobar_un_detectado_lo_deja_listo_para_el_daemon(db):  # noqa: F811
    r = _video(db, "a")
    fila = decidir(db, r.id, "aprobar")
    assert fila["status"] == "approved" and r.approved_at is not None


def test_descartar_lo_retira_para_que_no_vuelva_a_detectarse(db):  # noqa: F811
    r = _video(db, "b")
    assert decidir(db, r.id, "descartar")["status"] == "retired"


def test_reintentar_pone_a_cero_los_intentos(db):  # noqa: F811
    r = _video(db, "c", status="failed", attempts=3, error="yt-dlp 403")
    fila = decidir(db, r.id, "reintentar")
    assert fila["status"] == "approved" and fila["attempts"] == 0 and fila["error"] is None


@pytest.mark.parametrize("estado,accion", [
    ("done", "aprobar"), ("processing", "descartar"), ("detected", "reintentar"),
    ("done", "borrar"),
])
def test_no_se_salta_estados(db, estado, accion):  # noqa: F811
    r = _video(db, f"x-{estado}-{accion}", status=estado)
    with pytest.raises(AccionNoValida):
        decidir(db, r.id, accion)


def test_no_existe(db):  # noqa: F811
    with pytest.raises(LookupError):
        decidir(db, 999, "aprobar")


def test_listar_cuenta_exacto_y_ordena_por_nivel(db):  # noqa: F811
    _video(db, "sin-nivel")
    _video(db, "c1", nivel="C")
    # `voces` (ARRAY) no se puede guardar en el SQLite de los tests; `motivos` (JSON) sí.
    _video(db, "a1", nivel="A", motivos=["medio reconocido (RockFM)"])
    _video(db, "hecho", status="done")
    datos = listar(db)
    assert datos["cuenta"]["detected"] == 3 and datos["cuenta"]["done"] == 1
    assert [f["video_id"] for f in datos["filas"]["detected"]] == ["a1", "c1", "sin-nivel"]
    assert datos["filas"]["detected"][0]["motivos"] == ["medio reconocido (RockFM)"]


class _QdrantFalso:
    def __init__(self, colecciones=("interpretations_v1", "robe_voice_v1")):
        self.colecciones, self.borrados = set(colecciones), []

    def collection_exists(self, nombre):
        return nombre in self.colecciones

    def delete(self, collection_name, points_selector, wait=True):
        cond = points_selector.filter.must[0]
        self.borrados.append((collection_name, cond.key, cond.match.value))


def test_retirar_saca_la_fuente_sus_tramos_y_sus_vectores(db):  # noqa: F811
    from sqlalchemy import text

    from app.db.models import InterpretationSource, SourceSegment

    db.execute(text("PRAGMA foreign_keys=ON"))
    r = _video(db, "spam", status="done")
    fuente = InterpretationSource(kind=r.kind, url=r.url, title="Un Pais Magico - Tarragona")
    db.add(fuente)
    db.flush()
    db.add(SourceSegment(source_id=fuente.id, idx=0, start_s=0.0, end_s=4.0, text="hola"))
    db.commit()
    fid, qdrant = fuente.id, _QdrantFalso()

    fila = decidir(db, r.id, "retirar", qdrant=qdrant)

    assert fila["status"] == "retired"
    assert fila["retirada"] == {"fuente": fid, "puntos_borrados": True,
                                "consensos_que_la_citan": []}
    assert db.get(InterpretationSource, fid) is None
    assert db.query(SourceSegment).filter_by(source_id=fid).count() == 0
    assert sorted(qdrant.borrados) == [("interpretations_v1", "source_id", fid),
                                       ("robe_voice_v1", "source_id", fid)]


def test_retirar_sin_fuente_no_rompe(db):  # noqa: F811
    r = _video(db, "sin-fuente", status="done")
    fila = decidir(db, r.id, "retirar", qdrant=_QdrantFalso())
    assert fila["status"] == "retired" and fila["retirada"]["fuente"] is None


def test_solo_se_retira_lo_que_entro(db):  # noqa: F811
    r = _video(db, "pend", status="detected")
    with pytest.raises(AccionNoValida):
        decidir(db, r.id, "retirar", qdrant=_QdrantFalso())
