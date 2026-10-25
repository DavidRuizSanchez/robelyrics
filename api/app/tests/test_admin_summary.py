"""La portada del admin cuenta en la base de datos, no en listas recortadas.

Las colas de IG, clips y oportunidades se piden con límite; si la portada
contara esas listas, una cola de 600 diría «500» sin avisar.
"""
from __future__ import annotations

import pytest
from sqlalchemy import ARRAY, JSON, MetaData, Text, create_engine
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Session

from app.db.models import (
    ContentProposal,
    ErrataReport,
    InstagramQueueItem,
    NotificationDigest,
    Post,
    SeoOpportunity,
    SongInterpretation,
    SourceSegment,
    VideoClip,
    YouTubeIngestQueue,
)
from app.services.admin_summary import resumen
from app.services.instagram.config import MAX_PUBLISH_ATTEMPTS

MODELOS = (Post, ContentProposal, InstagramQueueItem, VideoClip, SeoOpportunity, ErrataReport,
           YouTubeIngestQueue, SourceSegment, SongInterpretation, NotificationDigest)


def _con_dependencias(tablas):
    """Las tablas pedidas más todas a las que apuntan sus claves foráneas."""
    pendientes, vistas = list(tablas), {}
    while pendientes:
        t = pendientes.pop()
        if t.name in vistas:
            continue
        vistas[t.name] = t
        pendientes.extend(fk.column.table for fk in t.foreign_keys)
    return list(vistas.values())


@pytest.fixture()
def db():
    """SQLite en memoria con las tablas de las colas (tipos Postgres traducidos)."""
    md = MetaData()
    for tabla in _con_dependencias([m.__table__ for m in MODELOS]):
        t = tabla.to_metadata(md)
        for col in t.columns:
            if isinstance(col.type, (JSONB, ARRAY)):
                col.type = JSON()
            elif isinstance(col.type, TSVECTOR):
                col.type = Text()
            sd = col.server_default
            if sd is not None and "::" in str(getattr(sd, "arg", "")):
                col.server_default = None
        t.indexes.clear()
    engine = create_engine("sqlite://")
    md.create_all(engine)
    with Session(engine) as s:
        yield s


def test_vacio_da_ceros_en_todas_las_colas(db):
    r = resumen(db)
    assert r["ideas"] == {"proposed": 0, "approved": 0, "scheduled": 0}
    assert r["instagram"]["needs_human"] == 0
    assert r["erratas"] == {"pending": 0, "needs_human": 0}
    assert r["corpus"] == {"detected": 0, "approved": 0, "failed": 0}


def test_cuenta_todo_sin_tope_y_separa_lo_que_pide_una_mano(db):
    from datetime import date

    for i in range(650):  # más que el límite de cualquier listado del panel
        db.add(InstagramQueueItem(day=date(2026, 10, 1), slot=1, position=i,
                                  status="pending", content_type="quote", title=f"t{i}"))
    db.add(InstagramQueueItem(day=date(2026, 10, 1), slot=1, position=900, status="prepared",
                              content_type="quote", title="mírame", needs_human=True))
    db.add(InstagramQueueItem(day=date(2026, 10, 1), slot=1, position=901, status="failed",
                              content_type="quote", title="agotado",
                              attempts=MAX_PUBLISH_ATTEMPTS))
    db.add(InstagramQueueItem(day=date(2026, 10, 1), slot=1, position=902, status="published",
                              content_type="quote", title="ya salió", needs_human=True))
    db.commit()

    ig = resumen(db)["instagram"]
    assert ig["pending"] == 650
    assert ig["needs_human"] == 1  # lo publicado ya no pide nada
    assert ig["failed_sin_intentos"] == 1
