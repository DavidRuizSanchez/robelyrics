"""Servicio de newsletter: dispatch de digests a suscriptores.

Estrategia de tracking: **per-subscriber, no per-post**.

Cada `Subscriber` tiene `last_sent_at` (timestamptz nullable). Para un
subscriber, los posts pendientes son los `published_at > last_sent_at` (o
todos los publicados si `last_sent_at IS NULL` — recién confirmado).

Esto permite:
- Que quien confirma tarde reciba la primera entrada ya publicada.
- Que el cron reenvíe solo los nuevos a quien ya está al día.
- Que sea idempotente: relanzar dos veces seguidas no duplica.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import Post, Subscriber
from app.services.email import (
    EmailError,
    render_newsletter_digest_email,
    send_email,
)

logger = logging.getLogger(__name__)

KIND_LABEL = {
    "editorial": "Editorial",
    "news": "Noticia",
    "anniversary": "Efeméride",
    "album-anniversary": "Aniversario",
    "spotlight": "Análisis",
    "evergreen": "Editorial",
}


def _site_url() -> str:
    return os.environ.get("SITE_URL", "https://entreinteriores.com").rstrip("/")


def _format_date_es(dt: datetime) -> str:
    months = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    return f"{dt.day} de {months[dt.month - 1]} de {dt.year}"


def _post_to_dict(p: Post, base_url: str) -> dict:
    return {
        "title": p.title,
        "excerpt": p.excerpt,
        "url": f"{base_url}/blog/{p.slug}",
        "kind_label": KIND_LABEL.get(p.kind, p.kind),
        "published_at_human": _format_date_es(p.published_at) if p.published_at else "",
    }


def posts_pending_for_subscriber(db: Session, sub: Subscriber) -> list[Post]:
    """Devuelve los posts publicados que el subscriber aún no ha recibido."""
    q = (
        db.query(Post)
        .filter(Post.status == "published")
        .filter(Post.published_at.isnot(None))
    )
    if sub.last_sent_at is not None:
        q = q.filter(Post.published_at > sub.last_sent_at)
    return q.order_by(Post.published_at.desc()).all()


def dispatch_to_subscriber(db: Session, sub: Subscriber) -> bool:
    """Si hay posts pendientes para ese subscriber, envía digest y actualiza
    `last_sent_at`. Devuelve True si envió, False si no había nada o falló."""
    if sub.status != "confirmed":
        return False

    pending = posts_pending_for_subscriber(db, sub)
    if not pending:
        return False

    base_url = _site_url()
    post_dicts = [_post_to_dict(p, base_url) for p in pending]
    unsubscribe_url = f"{base_url}/newsletter/baja?token={sub.unsubscribe_token}"
    html, text = render_newsletter_digest_email(post_dicts, unsubscribe_url, base_url)

    subject = (
        f"Una entrada nueva · {post_dicts[0]['title']}"
        if len(post_dicts) == 1
        else f"{len(post_dicts)} entradas nuevas en Entre Interiores"
    )

    try:
        send_email(to=sub.email, subject=subject, html=html, text=text)
    except EmailError as e:
        logger.warning("Newsletter send failed for %s: %s", sub.email, e)
        return False

    sub.last_sent_at = datetime.now(timezone.utc)
    db.flush()
    return True


def dispatch_for_post(db: Session, post_id: int) -> dict[str, int]:
    """Envía email con un único post a todos los subscribers confirmed.

    Idempotente: si `post.newsletter_dispatched_at` ya está rellenado, no-op.
    Diseñado para el flujo newsletter-on-publish (cap 2/semana). El cron
    diario `dispatch_to_all_confirmed` sigue funcionando como red de
    seguridad para posts donde este dispatcher falló o no se llamó.
    """
    post = db.query(Post).filter(Post.id == post_id).one_or_none()
    if post is None or post.status != "published":
        return {"sent": 0, "skipped": 0, "reason": "not-published"}
    if post.newsletter_dispatched_at is not None:
        return {"sent": 0, "skipped": 0, "reason": "already-dispatched"}

    subscribers = (
        db.query(Subscriber).filter(Subscriber.status == "confirmed").all()
    )
    base_url = _site_url()
    post_dict = _post_to_dict(post, base_url)
    subject = f"Una entrada nueva · {post.title}"

    sent = 0
    failed = 0
    now = datetime.now(timezone.utc)
    for sub in subscribers:
        unsubscribe_url = (
            f"{base_url}/newsletter/baja?token={sub.unsubscribe_token}"
        )
        html, text = render_newsletter_digest_email(
            [post_dict], unsubscribe_url, base_url
        )
        try:
            send_email(to=sub.email, subject=subject, html=html, text=text)
        except EmailError as e:
            logger.warning(
                "Newsletter dispatch_for_post failed for %s: %s", sub.email, e
            )
            failed += 1
            continue
        sub.last_sent_at = now
        sent += 1

    post.newsletter_dispatched_at = now
    db.commit()
    return {
        "subscribers_total": len(subscribers),
        "sent": sent,
        "failed": failed,
    }


def dispatch_to_all_confirmed(db: Session) -> dict[str, int]:
    """Itera todos los suscriptores confirmed y envía a quien tenga posts
    pendientes. Devuelve resumen con counts."""
    subscribers = (
        db.query(Subscriber).filter(Subscriber.status == "confirmed").all()
    )
    sent = 0
    no_pending = 0
    for sub in subscribers:
        if dispatch_to_subscriber(db, sub):
            sent += 1
        else:
            no_pending += 1
    db.commit()
    return {
        "subscribers_total": len(subscribers),
        "sent": sent,
        "no_pending": no_pending,
    }
