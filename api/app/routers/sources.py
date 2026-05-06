"""Endpoints para resolver fuentes de fan-content.

Auth obligatoria: las fuentes solo se exponen dentro de la capa privada
(/biblioteca/*). Cumple licencia CC-BY-NC-SA mostrando atribución por
fuente con link al original.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import InterpretationSource, User
from app.db.session import get_db
from app.services.auth import get_current_user

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceOut(BaseModel):
    id: int
    kind: str
    url: str
    title: str | None
    author: str | None
    published_at: datetime | None
    fetched_at: datetime
    quality_score: float | None


class SourceListItem(BaseModel):
    id: int
    kind: str
    url: str
    title: str | None
    author: str | None
    published_at: datetime | None


class SourceListOut(BaseModel):
    total: int
    items: list[SourceListItem]


@router.get("/{source_id}", response_model=SourceOut)
def get_source(
    source_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SourceOut:
    src = db.query(InterpretationSource).filter(InterpretationSource.id == source_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="source not found")
    return SourceOut(
        id=src.id,
        kind=src.kind,
        url=src.url,
        title=src.title,
        author=src.author,
        published_at=src.published_at,
        fetched_at=src.fetched_at,
        quality_score=src.quality_score,
    )


@router.get("", response_model=SourceListOut)
def list_sources(
    kind: str | None = Query(None, description="filtra por kind exacto"),
    ids: str | None = Query(
        None,
        description="bulk fetch: lista de IDs separados por coma (ej. '1,2,3')",
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SourceListOut:
    """Listado de fuentes para atribuciones o bulk fetch desde una canción."""
    q = db.query(InterpretationSource)

    if ids:
        try:
            id_list = [int(x) for x in ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="ids debe ser '1,2,3'") from None
        if not id_list:
            return SourceListOut(total=0, items=[])
        q = q.filter(InterpretationSource.id.in_(id_list))

    if kind:
        q = q.filter(InterpretationSource.kind == kind)

    total = q.count()
    rows = (
        q.order_by(InterpretationSource.kind, InterpretationSource.id)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return SourceListOut(
        total=total,
        items=[
            SourceListItem(
                id=r.id,
                kind=r.kind,
                url=r.url,
                title=r.title,
                author=r.author,
                published_at=r.published_at,
            )
            for r in rows
        ],
    )
