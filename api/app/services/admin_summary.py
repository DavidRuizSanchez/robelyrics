"""Recuento EXACTO de lo que espera una decisión, para la portada del admin.

Las pantallas de cada cola piden listas con límite (IG 100, clips 100,
oportunidades 500), así que contar sus filas en el panel daría cifras recortadas
sin avisar. Aquí todo sale de un COUNT en la base de datos.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import (
    ContentProposal,
    ErrataReport,
    InstagramQueueItem,
    Post,
    SeoOpportunity,
    VideoClip,
    YouTubeIngestQueue,
)
from app.services.instagram.config import MAX_PUBLISH_ATTEMPTS

_IG_VIVOS = ("proposed", "pending", "prepared", "failed")


def _por_estado(db: Session, modelo, *estados: str) -> dict[str, int]:
    filas = (
        db.query(modelo.status, func.count(modelo.id))
        .filter(modelo.status.in_(estados))
        .group_by(modelo.status)
        .all()
    )
    cuenta = {e: 0 for e in estados}
    cuenta.update({estado: int(n) for estado, n in filas})
    return cuenta


def resumen(db: Session) -> dict[str, dict[str, int]]:
    """Una entrada por panel; cada valor es un recuento exacto."""
    posts = _por_estado(db, Post, "pending_review", "scheduled")
    posts["bloqueadas"] = (
        db.query(func.count(Post.id))
        .filter(Post.status == "pending_review", Post.review_blocked_at.isnot(None))
        .scalar()
        or 0
    )

    ig = _por_estado(db, InstagramQueueItem, *_IG_VIVOS)
    ig["needs_human"] = (
        db.query(func.count(InstagramQueueItem.id))
        .filter(
            InstagramQueueItem.needs_human.is_(True),
            InstagramQueueItem.status.in_(_IG_VIVOS),
        )
        .scalar()
        or 0
    )
    # Fallidas que ya no se reintentan solas: esas sí piden una mano.
    ig["failed_sin_intentos"] = (
        db.query(func.count(InstagramQueueItem.id))
        .filter(
            InstagramQueueItem.status == "failed",
            InstagramQueueItem.attempts >= MAX_PUBLISH_ATTEMPTS,
        )
        .scalar()
        or 0
    )

    return {
        "ideas": _por_estado(db, ContentProposal, "proposed", "approved", "scheduled"),
        "entradas": posts,
        "instagram": ig,
        "clips": _por_estado(db, VideoClip, "requested", "downloading", "ready", "failed"),
        "oportunidades": _por_estado(
            db, SeoOpportunity, "detected", "approved", "drafted", "failed"
        ),
        "erratas": _por_estado(db, ErrataReport, "pending", "needs_human"),
        "corpus": _por_estado(db, YouTubeIngestQueue, "detected", "approved", "failed"),
    }
