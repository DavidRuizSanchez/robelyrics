"""Servicio de publicación.

Política editorial: **nada se publica automáticamente**. Los scripts cron
crean posts en estado `pending_review` y envían email al admin con botones
de aprobar/rechazar (firmados con JWT) + enlace al panel admin. La
publicación efectiva ocurre cuando el admin aprueba — desde el email o
desde el panel.

API:
- `propose_for_review(post, notify=True)` → setea pending_review y manda
  mail con preview + acciones. Llamado por todos los scripts cron.
- `auto_publish_post(post)` → marca published, dispara newsletter
  on-publish, hace revalidate Next. Llamado por el endpoint admin (panel
  o mail one-click).
- `schedule_or_publish(post)` → DEPRECATED, alias de propose_for_review
  por compatibilidad con scripts viejos.
- `flush_scheduled_due(db)` → cron diario que promueve `scheduled` a
  `published` (legacy del flujo anterior con cap móvil; mantenido por si
  queda algún post encolado).
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
def propose_for_review(
    db: Session, post: Post, *, notify: bool = True
) -> PublishResult:
    """Pone el post en `pending_review` y manda email al admin (si notify).

    Idempotente: si ya está en pending_review, no rompe — el mail también
    se envía (al admin le sirve como recordatorio). Si está published o
    rejected, no-op.
    """
    if post.status in {"published", "rejected"}:
        logger.info(
            "Post %s ya está en estado terminal (%s); no se propone",
            post.id, post.status,
        )
        return {
            "action": post.status,
            "post_id": post.id,
            "scheduled_for": None,
        }
    if post.status != "pending_review":
        post.status = "pending_review"
        db.commit()
        db.refresh(post)

    if notify:
        _notify_admin_review(db, post)

    return {"action": "pending_review", "post_id": post.id, "scheduled_for": None}


def _notify_admin_review(db: Session, post: Post) -> None:
    """Manda un email al admin con TODOS los posts pending_review (incluido
    el que se acaba de crear), con botones aprobar/rechazar firmados.
    Si falla, log warning pero no aborta (el post queda en pending_review
    igualmente)."""
    admin_email = os.environ.get("ADMIN_EMAIL")
    if not admin_email:
        logger.info("ADMIN_EMAIL no configurado, salto notify admin review")
        return

    site_url = os.environ.get("SITE_URL", "https://entreinteriores.com").rstrip("/")
    admin_panel_url = f"{site_url}/biblioteca/admin/posts?status=pending_review"

    from app.services.auth import create_admin_action_token
    from app.services.email import (
        EmailError,
        render_admin_review_email,
        send_email,
    )

    pendings = (
        db.query(Post)
        .filter(Post.status == "pending_review")
        .order_by(Post.created_at.desc())
        .limit(10)
        .all()
    )
    if not pendings:
        return

    kind_label = {
        "editorial": "Editorial",
        "news": "Noticia",
        "anniversary": "Efeméride",
        "album-anniversary": "Aniversario de disco",
        "spotlight": "Spotlight",
        "evergreen": "Evergreen",
    }

    items = []
    for p in pendings:
        approve_token = create_admin_action_token(p.id, "approve")
        reject_token = create_admin_action_token(p.id, "reject")
        items.append({
            "title": p.title,
            "kind_label": kind_label.get(p.kind, p.kind),
            "excerpt": p.excerpt,
            "source_name": p.source_name,
            "source_url": p.source_url,
            "approve_url": f"{site_url}/api/public/admin-action?token={approve_token}",
            "reject_url": f"{site_url}/api/public/admin-action?token={reject_token}",
            "admin_url": f"{site_url}/biblioteca/admin/posts/{p.id}"
            if False  # endpoint de detalle por id pendiente — link a lista por ahora
            else f"{site_url}/biblioteca/admin/posts?status=pending_review",
        })

    html, text = render_admin_review_email(items, admin_panel_url)
    subject = (
        f"📰 Una entrada para revisar — «{pendings[0].title}»"
        if len(pendings) == 1
        else f"📰 {len(pendings)} entradas para revisar en Entre Interiores"
    )
    try:
        send_email(to=admin_email, subject=subject, html=html, text=text)
        logger.info("Admin review email enviado (%d pendings)", len(pendings))
    except EmailError as exc:
        logger.warning("Admin review email failed: %s", exc)


def auto_publish_post(db: Session, post: Post) -> PublishResult:
    """Marca el post como publicado, lanza newsletter y revalida Next.js.

    Llamado:
      - Desde el endpoint admin (panel `/admin/posts/{id}/publish`).
      - Desde `/public/admin-action?token=...` (one-click desde email).
      - Desde flush_scheduled_due (legacy del flujo con cap).
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
    """DEPRECATED: alias de `propose_for_review`. Nada se publica automáticamente.

    Mantenido para compatibilidad con scripts/llamadores anteriores; nuevos
    usos deben llamar directamente a `propose_for_review`.
    """
    return propose_for_review(db, post)


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
