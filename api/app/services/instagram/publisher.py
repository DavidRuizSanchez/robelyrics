"""Orquestador de publicación en Instagram.

prepare:  tema → comentario editorial + verso de Robe + imagen → caption +
          fichero de imagen (sin publicar todavía).
publish:  sube la imagen a Cloudinary → publica vía Graph API → registra el
          resultado en `instagram_queue`.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem, Post
from app.services.instagram import (
    captions,
    cloudinary_upload,
    config,
    editorial,
    graph_api,
    imaging,
    photo_finder,
)

logger = logging.getLogger(__name__)

BLOG_BASE_URL = f"{config.SITE_URL}/blog"


def _topic_from_item(db: Session, item: InstagramQueueItem) -> dict:
    """Construye el dict de tema que consumen editorial / imaging / captions."""
    topic = {
        "title": item.title,
        "category": item.category or "Actualidad",
        "summary": item.summary or "",
        "source": item.source_name or "",
        "url": item.source_url or "",
    }
    if item.blog_post_id:
        post = db.get(Post, item.blog_post_id)
        if post is not None:
            topic["category"] = "Blog"
            topic["url"] = f"{BLOG_BASE_URL}/{post.slug}"
            topic["image_hint"] = post.hero_image_url or ""
            if not topic["summary"]:
                topic["summary"] = post.excerpt or ""
    return topic


def prepare(db: Session, item: InstagramQueueItem) -> InstagramQueueItem:
    """Genera imagen y caption para un item de la cola (sin publicar)."""
    topic = _topic_from_item(db, item)
    is_blog = topic.get("category") == "Blog"

    # Las noticias se reescriben con voz editorial propia (sin citar al medio);
    # los posts del blog ya traen su propio texto y no se reescriben.
    if not is_blog:
        editorial.enrich(topic)
        # Foto real con licencia libre (Wikimedia Commons), buscada en vivo.
        foto = photo_finder.find(topic)
        if foto:
            topic["image_hint"] = foto["url"]
            topic["image_credit"] = foto["credit"]

    image_path, used_hero = imaging.generate(topic, slot=item.slot or 1)
    # Solo se acredita la foto si finalmente se usó una imagen real con
    # licencia; si la generación cayó al fondo IA, no hay crédito que poner.
    if not used_hero:
        topic.pop("image_credit", None)
    item.image_path = image_path
    item.caption = captions.build(db, topic)
    item.status = "prepared"
    item.error = None
    db.commit()
    return item


def publish(
    db: Session, item: InstagramQueueItem, dry_run: bool = False
) -> InstagramQueueItem:
    """Publica un item ya preparado (lo prepara si hace falta)."""
    if not item.image_path or not os.path.exists(item.image_path):
        prepare(db, item)

    if dry_run:
        item.status = "prepared"
        db.commit()
        logger.info("[DRY-RUN] item %s listo (no se publica).", item.id)
        return item

    # Verificar el token antes de gastar cuota de la API.
    ok, msg = graph_api.token_is_valid()
    if not ok:
        item.status = "failed"
        item.error = msg
        db.commit()
        logger.error("[IG] token no válido para publicar: %s", msg)
        return item

    # Subir la imagen a Cloudinary (la Graph API exige una URL pública).
    try:
        image_url = cloudinary_upload.upload(item.image_path)
    except Exception as exc:  # noqa: BLE001
        item.status = "failed"
        item.error = f"Cloudinary: {exc}"
        db.commit()
        logger.error("[IG] subida a Cloudinary falló: %s", exc)
        return item
    item.image_url = image_url
    db.commit()

    media_id, result_msg = graph_api.post_photo(image_url, item.caption or "")
    if media_id:
        item.status = "published"
        item.ig_media_id = media_id
        item.published_at = datetime.now(timezone.utc)
        item.error = None
        logger.info("[IG] ✅ item %s publicado · media_id=%s", item.id, media_id)
    else:
        item.status = "failed"
        item.error = result_msg
        logger.error("[IG] ❌ item %s falló: %s", item.id, result_msg)
    db.commit()
    return item


def next_pending(db: Session) -> InstagramQueueItem | None:
    """Siguiente item a publicar: por slot (blog primero), día y antigüedad."""
    return db.execute(
        select(InstagramQueueItem)
        .where(InstagramQueueItem.status.in_(("pending", "prepared")))
        .order_by(
            InstagramQueueItem.slot,
            InstagramQueueItem.day,
            InstagramQueueItem.created_at,
        )
        .limit(1)
    ).scalar_one_or_none()
