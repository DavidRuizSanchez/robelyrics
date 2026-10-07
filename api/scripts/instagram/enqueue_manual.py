"""Encola un post de Instagram con MATERIAL PROPIO y caption escrito a mano.

    python -m scripts.instagram.enqueue_manual \
        --blog-slug mi-post --title "..." --caption-file c.txt \
        --images a.png b.png c.png --publish-at "2026-10-08 09:00"

Cubre un hueco real: `POST /admin/instagram/enqueue` exige `news_item_id` o
`blog_post_id` y además genera la imagen por su cuenta, así que no había forma de
encolar un carrusel con piezas hechas a mano. La alternativa era subir a
Cloudinary y llamar a `graph_api.post_carousel` a pelo, que se salta la cola, el
goteo, los reintentos y el registro.

Esto entra por la cola, con tres consecuencias que importan:

  · **`media_locked = True`**: `prepare` no vuelve a generar nada encima. Las
    piezas que se suben aquí son las que salen.
  · **Las piezas llevan `url` y no `local_path`**, igual que los clips que baja
    el daemon de la Mac. `_media_lista` las da por buenas, así que un reintento
    tras un fallo de Meta NO vuelve a subir nada a Cloudinary.
  · **`publish_at` lo publica `due_pinned`**, que dispara en el primer pase del
    cron posterior a esa hora. Con el cron cada 15 minutos, la ventana real es de
    un cuarto de hora.

El caption NO lo escribe un modelo: viene de un fichero. Por eso se pasa por
`tono_guard.moldes_en` antes de guardarlo y se avisa si trae fórmulas.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db.models import InstagramQueueItem, InstagramQueueMedia, Post
from app.db.session import SessionLocal
from app.services.instagram import config
from app.services.instagram import cloudinary_upload as cu

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MADRID = ZoneInfo("Europe/Madrid")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--blog-slug", required=True, help="post del blog al que acompaña")
    ap.add_argument("--title", required=True)
    ap.add_argument("--caption-file", required=True)
    ap.add_argument("--images", nargs="+", required=True, help="en orden de carrusel")
    ap.add_argument("--publish-at", required=True, help="'2026-10-08 09:00', hora de Madrid")
    ap.add_argument("--content-type", default="blog")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    caption = Path(args.caption_file).read_text(encoding="utf-8").strip()
    if len(caption) > 2200:
        logger.error("el caption mide %d caracteres y Meta corta en 2.200", len(caption))
        return 1

    from app.services.instagram import tono_guard as tg
    moldes = tg.moldes_en(caption)
    if moldes:
        logger.warning("el caption trae fórmulas de molde: %s", moldes)

    rutas = [Path(i) for i in args.images]
    faltan = [str(r) for r in rutas if not r.exists()]
    if faltan:
        logger.error("no existen: %s", faltan)
        return 1

    cuando = datetime.strptime(args.publish_at, "%Y-%m-%d %H:%M").replace(tzinfo=MADRID)
    tipo = "CAROUSEL" if len(rutas) >= 2 else "IMAGE"

    with SessionLocal() as db:
        post = db.execute(select(Post).where(Post.slug == args.blog_slug)).scalar_one_or_none()
        if post is None:
            logger.error("no hay post con slug %s", args.blog_slug)
            return 1
        if post.status != "published":
            logger.error("el post está en %s: no se encola algo que no está publicado",
                         post.status)
            return 1

        ya = db.execute(select(InstagramQueueItem).where(
            InstagramQueueItem.content_key == f"manual:{args.blog_slug}")).scalar_one_or_none()
        if ya:
            logger.error("ya existe el item %s para este post (estado %s)", ya.id, ya.status)
            return 1

        logger.info("post %s · %d piezas · %s · %s",
                    post.id, len(rutas), tipo, cuando.isoformat())
        if args.dry_run:
            logger.info("dry-run: no se sube ni se escribe nada")
            return 0

        subidas = []
        for r in rutas:
            url = cu.upload(str(r), folder="entreinteriores-ig")
            if not url:
                logger.error("Cloudinary no devolvió URL para %s. Se aborta.", r.name)
                return 1
            logger.info("  subida %s", r.name)
            subidas.append(url)

        item = InstagramQueueItem(
            blog_post_id=post.id,
            # `day` es NOT NULL y `slot` su hueco dentro del día: el planner los
            # usa para ordenar. Sin ellos el insert revienta DESPUÉS de haber
            # subido las imágenes a Cloudinary, que es la peor forma de fallar.
            day=cuando.date(),
            slot=0,
            content_type=args.content_type,
            content_key=f"manual:{args.blog_slug}",
            title=args.title[:300],
            summary=(post.excerpt or "")[:600] or None,
            source_url=f"https://entreinteriores.com/blog/{post.slug}",
            caption=caption,
            media_type=tipo,
            media_locked=True,
            image_url=subidas[0],
            publish_at=cuando,
            publish_on=cuando.date(),
            status="pending",
            needs_human=False,
        )
        db.add(item)
        db.flush()
        for i, url in enumerate(subidas):
            db.add(InstagramQueueMedia(item_id=item.id, position=i, kind="image",
                                       role="cover" if i == 0 else None, url=url))
        db.commit()
        logger.info("encolado item %s · sale el %s (hora de Madrid)",
                    item.id, cuando.strftime("%d-%m-%Y a las %H:%M"))
        logger.info("el cron corre cada %s min, así que la ventana real es de ese tamaño",
                    getattr(config, "CRON_MINUTES", 15))
    return 0


if __name__ == "__main__":
    sys.exit(main())
