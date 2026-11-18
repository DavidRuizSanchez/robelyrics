"""El sitemap lleva TODOS los posts publicados (18-11-2026).

Tiraba de `/public/posts`, que tiene límite (30 por defecto): con 45 publicados, los 15
más antiguos habían salido del sitemap, y con ellos del monitor de cambios y de la
auditoría del JSON-LD, que lo recorren.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Response

from app.db.models import Post
from app.routers import public
from app.tests.test_admin_summary import _con_dependencias


@pytest.fixture()
def db():
    from sqlalchemy import ARRAY, JSON, MetaData, Text, create_engine
    from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
    from sqlalchemy.orm import Session

    md = MetaData()
    for tabla in _con_dependencias([Post.__table__]):
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


def _posts(db, n: int, *, status: str = "published") -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(n):
        db.add(Post(slug=f"{status}-{i}", kind="evergreen", status=status, title=f"Post {i}",
                    body_md="texto", published_at=base + timedelta(days=i)))
    db.commit()


def test_el_sitemap_trae_todos_los_publicados(db):
    _posts(db, 45)
    _posts(db, 3, status="approved")
    assert len(public.public_posts_list(Response(), db)) == 30   # el listado sigue con tope
    slugs = [p.slug for p in public.public_posts_sitemap(Response(), db)]
    assert len(slugs) == 45
    assert "published-0" in slugs               # el más antiguo: el que se caía
    assert not any(s.startswith("approved") for s in slugs)
