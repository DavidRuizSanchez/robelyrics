"""Tarea diaria del pipeline de Instagram.

Selecciona los temas del día desde `news_items`, encola los posts de noticias
y difunde los artículos nuevos del blog. Deja todo preparado (imagen + caption)
para que `publish_next` solo tenga que publicar.

Pensado para correr una vez al día (cron, p.ej. 08:00).

Uso:
    python -m scripts.instagram.prepare_daily
    python -m scripts.instagram.prepare_daily --dry-run   (no llama a la IA de imagen)
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models import InstagramQueueItem, Post
from app.db.session import SessionLocal
from app.services.instagram import config, publisher, topics

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Slot bajo para que los posts del blog tengan prioridad en la cola.
BLOG_SLOT = 0
# Solo se difunden artículos del blog publicados en los últimos N días, para
# no inundar Instagram con el histórico la primera vez que corre.
BLOG_LOOKBACK_DAYS = 2


def _enqueue_news(db, today: date, prepare: bool) -> int:
    """Encola los posts de noticias del día. Devuelve cuántos."""
    already = db.execute(
        select(InstagramQueueItem.id).where(
            InstagramQueueItem.day == today,
            InstagramQueueItem.slot >= 1,
        )
    ).first()
    if already is not None:
        logger.info("Ya había posts de noticias para hoy; no se duplican.")
        return 0

    temas = topics.select(db, count=config.POSTS_PER_DAY)
    logger.info("%d temas seleccionados:", len(temas))
    queued = 0
    for slot, tema in enumerate(temas, start=1):
        item = InstagramQueueItem(
            news_item_id=tema.get("news_item_id"),
            day=today,
            slot=slot,
            title=tema["title"][:300],
            category=tema.get("category"),
            summary=tema.get("summary"),
            source_name=tema.get("source"),
            source_url=tema.get("url") or None,
            status="pending",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("  %d. [%s] %s", slot, item.category, item.title)
        if prepare:
            try:
                publisher.prepare(db, item)
            except Exception as exc:  # noqa: BLE001
                logger.error("  No se pudo preparar el item %s: %s", item.id, exc)
        queued += 1
    return queued


def _enqueue_blog(db, today: date, prepare: bool) -> int:
    """Encola posts de IG para los artículos nuevos del blog. Devuelve cuántos."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=BLOG_LOOKBACK_DAYS)
    nuevos = db.execute(
        select(Post)
        .where(
            Post.status == "published",
            Post.published_at.is_not(None),
            Post.published_at >= cutoff,
        )
        .order_by(Post.published_at)
    ).scalars().all()

    ya_difundidos = set(
        db.execute(
            select(InstagramQueueItem.blog_post_id).where(
                InstagramQueueItem.blog_post_id.is_not(None)
            )
        ).scalars().all()
    )

    queued = 0
    for post in nuevos:
        if post.id in ya_difundidos:
            continue
        item = InstagramQueueItem(
            blog_post_id=post.id,
            day=today,
            slot=BLOG_SLOT,
            title=post.title[:300],
            category="Blog",
            summary=post.excerpt,
            source_name="Entre Interiores · Blog",
            source_url=f"{config.SITE_URL}/blog/{post.slug}",
            status="pending",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("  Blog: «%s» encolado", post.title)
        if prepare:
            try:
                publisher.prepare(db, item)
            except Exception as exc:  # noqa: BLE001
                logger.error("  No se pudo preparar el post del blog %s: %s", item.id, exc)
        queued += 1
    return queued


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo encola; no genera imágenes ni captions.",
    )
    args = parser.parse_args()
    prepare = not args.dry_run

    today = date.today()
    logger.info("Pipeline Instagram · tarea diaria · %s", today)

    with SessionLocal() as db:
        news = _enqueue_news(db, today, prepare)
        blog = _enqueue_blog(db, today, prepare)

    logger.info(
        "Tarea diaria completada: %d posts de noticias + %d del blog encolados.",
        news, blog,
    )


if __name__ == "__main__":
    main()
