"""Servicio de publicación con cap móvil de 2 posts/semana.

Política:
- Aniversarios (`kind` en {`anniversary`, `album-anniversary`}) se publican
  **siempre** en el día correspondiente. Son excepción al cap porque tienen
  fecha exacta que no se puede aplazar.
- El resto de kinds (news, spotlight, evergreen, editorial) respetan un cap
  móvil: como máximo 2 publicaciones en los últimos 7 días.
- Cuando el cap está lleno, el post entra como `status='scheduled'` con
  `scheduled_for` calculado al primer hueco libre. El cron
  `flush_scheduled_due` los promueve a `published` cuando llega su momento.

Tras publicar, dispara newsletter on-publish y revalidación de Next.js.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import TypedDict

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import Post
from app.services.newsletter import dispatch_for_post

logger = logging.getLogger(__name__)

WEEKLY_CAP = 2
WINDOW_DAYS = 7

# Kinds que ignoran el cap porque tienen fecha calendario obligatoria.
CAP_EXEMPT_KINDS = {"anniversary", "album-anniversary"}


class PublishResult(TypedDict):
    action: str  # "published" | "scheduled"
    post_id: int
    scheduled_for: datetime | None


# --------------------------------------------------------------------------- #
# Núcleo: scheduler
# --------------------------------------------------------------------------- #
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _occupied_dates(db: Session, *, look_ahead_days: int = 60) -> list[datetime]:
    """Devuelve las fechas relevantes para calcular el cap.

    Incluye:
      - Publicados en los últimos 7+ días (necesario para ver si llenan ventana).
      - Scheduled futuros (porque cuentan al hueco que ocuparán).
    Excluye aniversarios — no cuentan contra el cap.
    """
    now = _now()
    horizon_past = now - timedelta(days=WINDOW_DAYS + 1)
    horizon_future = now + timedelta(days=look_ahead_days)

    rows = (
        db.query(Post.kind, Post.status, Post.published_at, Post.scheduled_for)
        .filter(
            or_(
                (Post.status == "published") & (Post.published_at >= horizon_past),
                (Post.status == "scheduled") & (Post.scheduled_for > now) & (Post.scheduled_for < horizon_future),
            )
        )
        .all()
    )
    dates: list[datetime] = []
    for kind, status, pub_at, sched_at in rows:
        if kind in CAP_EXEMPT_KINDS:
            continue
        dt = pub_at if status == "published" else sched_at
        if dt is not None:
            dates.append(dt)
    dates.sort()
    return dates


def _next_publish_slot(db: Session) -> datetime:
    """Primer instante a partir de `now()` donde, contando publicados y
    scheduled, la ventana de 7 días previos tiene `< WEEKLY_CAP` posts no
    exentos.
    """
    now = _now()
    dates = _occupied_dates(db)
    candidate = now

    # Avanza candidate iterativamente. Cada iteración salta al momento en que
    # el siguiente post deja la ventana de 7 días.
    for _ in range(50):  # cota de seguridad
        window_start = candidate - timedelta(days=WINDOW_DAYS)
        in_window = [d for d in dates if window_start < d <= candidate]
        if len(in_window) < WEEKLY_CAP:
            return candidate
        # Lleno. Avanza al momento en que sale el más antiguo de la ventana.
        oldest_in_window = min(in_window)
        candidate = oldest_in_window + timedelta(days=WINDOW_DAYS, minutes=1)

    # Fallback defensivo
    logger.warning("publishing._next_publish_slot saturó 50 iteraciones")
    return now + timedelta(days=WINDOW_DAYS)


# --------------------------------------------------------------------------- #
# Hooks post-publicación
# --------------------------------------------------------------------------- #
def _revalidate_next(slug: str) -> None:
    """Pide a Next.js que revalide /blog y /blog/{slug}. No bloquea si falla."""
    token = os.environ.get("REVALIDATE_TOKEN")
    if not token:
        logger.info("REVALIDATE_TOKEN no configurado, salto revalidate")
        return
    base = os.environ.get("WEB_INTERNAL_URL", "http://web:3000").rstrip("/")
    url = f"{base}/api/revalidate"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                url,
                headers={"X-Revalidate-Token": token},
                json={"paths": ["/blog", f"/blog/{slug}"], "tags": ["posts"]},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Revalidate failed for /blog/%s: %s", slug, exc)


def _dispatch_newsletter(db: Session, post_id: int) -> None:
    """Llama al dispatcher de newsletter. Aislado en try/except para no
    abortar la publicación si SMTP falla — el cron diario hará catch-up."""
    try:
        dispatch_for_post(db, post_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Newsletter dispatch_for_post falló para post %s: %s", post_id, exc
        )


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
def auto_publish_post(db: Session, post: Post) -> PublishResult:
    """Marca el post como publicado, lanza newsletter y revalida Next.js.

    Llamado:
      - Directamente desde schedule_or_publish cuando hay hueco.
      - Desde flush_scheduled_due cuando un scheduled madura.
      - Desde el endpoint admin manual de publish (igual flujo).
    """
    if post.status != "published":
        post.status = "published"
        post.published_at = _now()
        post.scheduled_for = None
        db.flush()
    db.commit()
    db.refresh(post)

    _dispatch_newsletter(db, post.id)
    _revalidate_next(post.slug)

    return {"action": "published", "post_id": post.id, "scheduled_for": None}


def schedule_or_publish(db: Session, post: Post) -> PublishResult:
    """Decide si publicar inmediatamente o encolar según el cap móvil.

    El post debe estar persistido (con id). Si el cap permite, lo publica al
    instante. Si no, lo deja como `scheduled` con `scheduled_for` calculado.
    """
    if post.kind in CAP_EXEMPT_KINDS:
        return auto_publish_post(db, post)

    now = _now()
    seven_ago = now - timedelta(days=WINDOW_DAYS)
    recent = (
        db.query(Post)
        .filter(Post.status == "published")
        .filter(Post.published_at >= seven_ago)
        .filter(~Post.kind.in_(CAP_EXEMPT_KINDS))
        .count()
    )
    if recent < WEEKLY_CAP:
        return auto_publish_post(db, post)

    slot = _next_publish_slot(db)
    post.status = "scheduled"
    post.scheduled_for = slot
    db.commit()
    db.refresh(post)
    logger.info(
        "Post %s '%s' encolado para %s (cap %d/%d en últimos %d días)",
        post.id, post.slug, slot.isoformat(), recent, WEEKLY_CAP, WINDOW_DAYS,
    )
    return {"action": "scheduled", "post_id": post.id, "scheduled_for": slot}


def flush_scheduled_due(db: Session) -> dict[str, int]:
    """Publica todos los posts en estado `scheduled` cuyo `scheduled_for`
    ya pasó. Llamado por cron diario.
    """
    now = _now()
    due = (
        db.query(Post)
        .filter(Post.status == "scheduled")
        .filter(Post.scheduled_for.isnot(None))
        .filter(Post.scheduled_for <= now)
        .order_by(Post.scheduled_for)
        .all()
    )
    published = 0
    for post in due:
        # Re-check del cap antes de publicar (puede que se haya llenado por
        # otras vías mientras estaba encolado).
        seven_ago = now - timedelta(days=WINDOW_DAYS)
        cnt = (
            db.query(Post)
            .filter(Post.status == "published")
            .filter(Post.published_at >= seven_ago)
            .filter(~Post.kind.in_(CAP_EXEMPT_KINDS))
            .count()
        )
        if cnt >= WEEKLY_CAP:
            new_slot = _next_publish_slot(db)
            post.scheduled_for = new_slot
            db.commit()
            logger.info(
                "Post %s re-encolado a %s (cap saturado al despertar)",
                post.id, new_slot.isoformat(),
            )
            continue
        auto_publish_post(db, post)
        published += 1
    return {"due": len(due), "published": published}
