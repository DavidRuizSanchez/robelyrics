"""Retroactivo: re-asigna la imagen heroica de los posts a la de su ENTIDAD
PROTAGONISTA (relevante por construcción), sustituyendo las imágenes
irrelevantes de búsquedas antiguas a ciegas en Wikimedia. Limpia además la
línea de atribución antigua que se incrustaba al final del cuerpo (ahora la
atribución se muestra en el figcaption).

Uso:
  python -m scripts.blog.refresh_hero_images --dry-run
  python -m scripts.blog.refresh_hero_images
  python -m scripts.blog.refresh_hero_images --slug <slug>
"""
from __future__ import annotations

import argparse
import logging

from app.db.models import Post
from app.db.session import SessionLocal
from app.services.blog_hero import used_hero_urls
from app.services.hero_image import pick_hero_image
from app.services.hero_io import apply_hero

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _strip_old_attribution(body: str, old_attr: str | None) -> str:
    if not old_attr or not body:
        return body
    for variant in (f"\n\n{old_attr}\n", f"\n\n{old_attr}", f"\n{old_attr}", old_attr):
        if variant in body:
            return body.replace(variant, "").rstrip() + "\n"
    return body


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with SessionLocal() as db:
        q = db.query(Post).filter(Post.status == "published")
        if args.slug:
            q = q.filter(Post.slug == args.slug)
        posts = q.all()
        # Dedup ACTIVO: nunca dos posts con la misma imagen. Arrancamos del conjunto
        # de URLs ya en uso y lo vamos actualizando conforme reasignamos, para que la
        # dedup valga también entre posts de este mismo barrido.
        used = used_hero_urls(db)
        changed = 0
        for p in posts:
            own = p.hero_image_url
            candidate_used = (used - {own}) if own else used
            subject = (p.target_keyword or p.title or "").strip()
            img = pick_hero_image(db, p.entities, used=candidate_used, subject=subject)
            if not img:
                logger.info("  – %-50s sin imagen de entidad libre (se deja)", p.slug[:50])
                continue
            if img["url"] == p.hero_image_url:
                continue
            logger.info("  ✓ %-50s [%s] → [%s]", p.slug[:50],
                        (p.hero_image_attribution or "—")[:25], (img["attribution"] or "—")[:25])
            if args.dry_run:
                changed += 1
                continue
            p.body_md = _strip_old_attribution(p.body_md, p.hero_image_attribution)
            apply_hero(p, img)  # los 5 campos juntos (incluido alt), sin desincronizar
            if own:
                used.discard(own)
            used.add(img["url"])
            changed += 1
        if not args.dry_run:
            db.commit()
        logger.info("Posts actualizados: %d / %d", changed, len(posts))


if __name__ == "__main__":
    main()
