"""Orquestador de publicación en Instagram.

prepare:  tema → comentario editorial + verso de Robe + imagen → caption +
          fichero de imagen (sin publicar todavía).
publish:  sube la imagen a Cloudinary → publica vía Graph API → registra el
          resultado en `instagram_queue`.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem, Person, Post
from app.services.instagram import (
    album_cover,
    captions,
    cloudinary_upload,
    config,
    editorial,
    graph_api,
    imaging,
    photo_finder,
    robe_quote,
    tone,
)
from app.services.instagram.evergreen import EVERGREEN_TYPES

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


def _clean_credit(raw: str) -> str:
    """Pasa una atribución en markdown (pensada para la web) a texto plano apto
    para el caption de Instagram: sin markdown, sin enlaces y sin raya larga."""
    txt = (raw or "").strip()
    txt = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", txt)   # [texto](url) -> texto
    txt = txt.replace("*", "").replace("_", "")
    txt = re.sub(r"\s*[—–]\s*", " · ", txt)              # raya larga -> punto medio
    txt = re.sub(r"^\s*foto:\s*", "", txt, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", txt).strip(" ·")


def _apply_person_photo(
    db: Session, item: InstagramQueueItem, topic: dict
) -> None:
    """Para una efeméride de persona, usa la foto curada de su ficha en la web.

    El `content_key` de los cumpleaños/aniversarios natales es
    `ephemeris:birth_<slug>_<año>`. Si la persona tiene `image_url`, se reusa esa
    misma imagen (la que ya sale en /personas/<slug>): garantiza que la cara es
    la correcta (sin homónimos) y respeta su atribución CC.
    """
    key = item.content_key or ""
    prefix = "ephemeris:birth_"
    if not key.startswith(prefix):
        return
    slug = key[len(prefix):].rsplit("_", 1)[0]
    if not slug:
        return
    person = db.execute(
        select(Person).where(Person.slug == slug)
    ).scalar_one_or_none()
    if person is None or not person.image_url:
        return
    url = person.image_url
    if url.startswith("/"):
        url = config.SITE_URL + url
    topic["image_hint"] = url
    topic["image_kind"] = "photo"
    attribution = _clean_credit(person.image_attribution or "")
    if attribution:
        lic = (person.image_license or "").strip()
        if lic and lic.lower() not in attribution.lower():
            attribution += f" · {lic}"
        topic["image_credit"] = attribution
    logger.info("[IG] efeméride de %s → foto de ficha %s", slug, url[:60])


def prepare(db: Session, item: InstagramQueueItem) -> InstagramQueueItem:
    """Genera imagen y caption para un item de la cola (sin publicar)."""
    topic = _topic_from_item(db, item)
    is_blog = item.content_type == "blog" or topic.get("category") == "Blog"
    is_evergreen = item.content_type in EVERGREEN_TYPES

    # El tono (sobrio vs neutral) gobierna CTA, emoji y prompt editorial.
    topic["tone"] = tone.classify(
        topic.get("title", ""), topic.get("summary", "")
    )

    if is_evergreen:
        # Evergreen: el contenido (verso/efeméride/anécdota/cita) ya es final y
        # sale del corpus verificado. NO se reescribe con IA (anti-alucinación)
        # ni se busca foto de prensa. Imagen, por prioridad:
        #   1) Portada del disco si el texto lo menciona (versos, efeméride de
        #      disco): el arte del propio disco al que pertenece.
        #   2) Efeméride de una PERSONA (cumpleaños/aniversario natal): SU foto
        #      curada de la ficha de la web (misma imagen, sin homónimos).
        #   3) Si no, arte temático (IA) afín a la categoría.
        cover = album_cover.find(db, topic)
        if cover:
            topic["image_hint"] = cover["url"]
            topic["image_kind"] = "cover"
        else:
            _apply_person_photo(db, item, topic)
        # El contenido se basta solo: sin verso ornamental (evita duplicarlo en
        # los posts de frase, donde el verso YA es el titular).
        topic["verse"] = {}
    else:
        # Las noticias se reescriben con voz editorial propia (sin citar al
        # medio); los posts del blog ya traen su texto y su imagen destacada.
        if not is_blog:
            editorial.enrich(topic)
            # Fuente de imagen por prioridad:
            #   1) Portada del disco si el tema trata sobre uno de la discografía.
            #   2) Foto CC del protagonista real (Wikimedia/Openverse) por entidad.
            #   3) (en imaging) arte IA temático como último recurso.
            cover = album_cover.find(db, topic)
            if cover:
                topic["image_hint"] = cover["url"]
                topic["image_kind"] = "cover"
            else:
                # Créditos de las fotos recientes: para no repetir imagen.
                recent_credits = {
                    m.group(1).strip()
                    for c in db.execute(
                        select(InstagramQueueItem.caption)
                        .where(
                            InstagramQueueItem.caption.is_not(None),
                            InstagramQueueItem.id != item.id,
                        )
                        .order_by(InstagramQueueItem.id.desc())
                        .limit(12)
                    ).scalars().all()
                    if c and (m := re.search(r"📷\s*(.+)", c))
                }
                foto = photo_finder.find(topic, exclude=recent_credits)
                if foto:
                    topic["image_hint"] = foto["url"]
                    topic["image_hint_thumb"] = foto.get("thumb") or ""
                    topic["image_credit"] = foto.get("credit") or ""
                    topic["image_kind"] = "photo"

        # Verso afín al tema (se reutiliza en imagen y caption, así coinciden).
        # Se excluyen los versos usados en los últimos posts para no repetirlos.
        _t = topic.get("headline") or topic.get("title") or ""
        _b = topic.get("caption_body") or topic.get("summary") or ""
        recent_caps = db.execute(
            select(InstagramQueueItem.caption)
            .where(InstagramQueueItem.caption.is_not(None), InstagramQueueItem.id != item.id)
            .order_by(InstagramQueueItem.id.desc())
            .limit(6)
        ).scalars().all()
        recent_verses = {
            m.group(1)
            for c in recent_caps
            if (m := re.search(r"«([^»]+)»", c or ""))
        }
        topic["verse"] = robe_quote.find_verse(
            db, f"{_t}. {_b}", exclude_lines=recent_verses
        ) or {}

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

    # Verificar token Y que la cuenta sea alcanzable (no solo el scope).
    ok, msg, _ = graph_api.connection_is_healthy()
    if not ok:
        item.status = "failed"
        item.error = msg
        db.commit()
        logger.error("[IG] conexión no saludable para publicar: %s", msg)
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
    """Siguiente item del GOTEO: orden manual (`position`) primero; luego slot
    (blog primero), día y antigüedad. Excluye el contenido con fecha fija
    (`publish_on`): ese no gotea, se publica su día vía `due_pinned`."""
    return db.execute(
        select(InstagramQueueItem)
        .where(
            InstagramQueueItem.status.in_(("pending", "prepared")),
            InstagramQueueItem.publish_on.is_(None),
        )
        .order_by(
            InstagramQueueItem.position,
            InstagramQueueItem.slot,
            InstagramQueueItem.day,
            InstagramQueueItem.created_at,
        )
        .limit(1)
    ).scalar_one_or_none()


def due_pinned(db: Session) -> list[InstagramQueueItem]:
    """Items con efeméride cuyo día es HOY (aniversarios, cumpleaños). Se
    publican su día exacto, al margen del cuentagotas."""
    today = date.today()
    return db.execute(
        select(InstagramQueueItem)
        .where(
            InstagramQueueItem.status.in_(("pending", "prepared")),
            InstagramQueueItem.publish_on == today,
        )
        .order_by(InstagramQueueItem.position, InstagramQueueItem.created_at)
    ).scalars().all()
