"""Panel de cambios del sitio (`/biblioteca/admin/cambios`).

Lo que detecta `scripts/seo/monitor_cambios.py`: qué página, qué campo, antes y
después, y si lo explica algo que hizo el propio sistema. Lo inesperado primero.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.db.models import ContentRevision, PageChange, PageMonitorRun, PageSnapshot, User
from app.db.session import get_db
from app.services.auth import get_current_admin

router = APIRouter(prefix="/admin/cambios", tags=["admin"])
Db = Annotated[Session, Depends(get_db)]
Admin = Annotated[User, Depends(get_current_admin)]

# El texto entero de una página no viaja al panel: el diff va en `detalle`.
_CAMPOS_LARGOS = {"contenido"}
_ORDEN = case((PageChange.severidad == "critico", 0), (PageChange.severidad == "estructural", 1),
              (PageChange.severidad == "contenido", 2), else_=3)


class MarcarIn(BaseModel):
    ids: list[int]


def _fila(c: PageChange, revertibles: set[str]) -> dict:
    largo = c.campo in _CAMPOS_LARGOS
    return {
        "id": c.id, "path": c.path, "campo": c.campo, "severidad": c.severidad,
        "antes": None if largo else c.antes, "despues": None if largo else c.despues,
        "detalle": c.detalle or {}, "causa": c.causa,
        "detected_at": c.detected_at.isoformat() if c.detected_at else None,
        "seen_at": c.seen_at.isoformat() if c.seen_at else None,
        "revertible": c.path in revertibles,
    }


@router.get("")
def listar(
    estado: Literal["sin_ver", "vistos", "todos"] = "sin_ver",
    tipo: Literal["inesperados", "esperados", "todos"] = "todos",
    campo: str | None = None,
    limit: int = 300,
    *,
    db: Db,
    _admin: Admin,
) -> dict:
    q = db.query(PageChange)
    if estado == "sin_ver":
        q = q.filter(PageChange.seen_at.is_(None))
    elif estado == "vistos":
        q = q.filter(PageChange.seen_at.isnot(None))
    if tipo == "inesperados":
        q = q.filter(PageChange.causa.is_(None))
    elif tipo == "esperados":
        q = q.filter(PageChange.causa.isnot(None))
    if campo:
        q = q.filter(PageChange.campo == campo)
    total = q.count()
    filas = (q.order_by(PageChange.causa.isnot(None), _ORDEN, PageChange.detected_at.desc(),
                        PageChange.path)
             .limit(max(1, min(limit, 1000))).all())
    revertibles = {p for (p,) in db.query(ContentRevision.path)
                   .filter(ContentRevision.reverted_at.is_(None),
                           ContentRevision.path.in_({f.path for f in filas})).all()}
    por_campo = dict(q.with_entities(PageChange.campo, func.count(PageChange.id))
                     .group_by(PageChange.campo).all())
    ultima = (db.query(PageMonitorRun).filter(PageMonitorRun.finished_at.isnot(None))
              .order_by(PageMonitorRun.id.desc()).first())
    return {
        "total": total,
        "por_campo": por_campo,
        "urls_vigiladas": db.query(func.count(PageSnapshot.id)).scalar() or 0,
        "ultima_pasada": None if ultima is None else {
            "finished_at": ultima.finished_at.isoformat(), "urls": ultima.urls,
            "changed_urls": ultima.changed_urls, "errors": ultima.errors,
            "baseline": ultima.baseline, "global_event": ultima.global_event,
            "notified": ultima.notified_at is not None,
        },
        "filas": [_fila(c, revertibles) for c in filas],
    }


@router.post("/visto")
def marcar_vistos(payload: MarcarIn, db: Db, _admin: Admin) -> dict:
    if not payload.ids:
        raise HTTPException(status_code=400, detail="sin ids")
    n = (db.query(PageChange)
         .filter(PageChange.id.in_(payload.ids), PageChange.seen_at.is_(None))
         .update({PageChange.seen_at: datetime.now(UTC)}, synchronize_session=False))
    db.commit()
    return {"marcados": n}
