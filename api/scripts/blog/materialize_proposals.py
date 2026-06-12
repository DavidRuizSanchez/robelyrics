"""Materializa las propuestas programadas: cuando llega su `scheduled_for`,
crea el `Post` desde el borrador ya generado y lo publica.

Cron diario. Para cada `ContentProposal` con status='scheduled' y
`scheduled_for <= hoy`:
  1. Se asegura de que tenga borrador (`body_md`). Normalmente ya se generó al
     APROBARLA (`draft_generator.generate_proposal_draft`); si no, lo genera
     ahora como red de seguridad.
  2. Crea el `Post` copiando el borrador (cuerpo, foto, meta, entidades ya
     saneados y enlazados) y lo publica vía `auto_publish_post`.
  3. Marca la propuesta como `used` con `post_id`.

Uso:
    python -m scripts.blog.materialize_proposals
    python -m scripts.blog.materialize_proposals --dry-run
"""
from __future__ import annotations

import argparse
import logging
import re
import unicodedata
from datetime import date

from sqlalchemy import select

from app.db.models import ContentProposal, Post
from app.db.session import SessionLocal
from app.services.draft_generator import generate_proposal_draft
from app.services.publishing import auto_publish_post

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _slugify(text: str, max_len: int = 90) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    ascii_only = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return ascii_only[:max_len] or "post"


def _unique_slug(db, base: str) -> str:
    slug = base
    i = 2
    while db.execute(select(Post).where(Post.slug == slug)).scalar_one_or_none():
        slug = f"{base}-{i}"
        i += 1
    return slug


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    today = date.today()
    with SessionLocal() as db:
        due = (
            db.query(ContentProposal)
            .filter(ContentProposal.status == "scheduled")
            .filter(ContentProposal.scheduled_for.isnot(None))
            .filter(ContentProposal.scheduled_for <= today)
            .order_by(ContentProposal.scheduled_for)
            .all()
        )
        logger.info("Propuestas a materializar hoy: %d", len(due))

        for p in due:
            logger.info("[%s] %s (programada %s)", p.kind, p.title, p.scheduled_for)
            if args.dry_run:
                continue

            # 1. Asegurar borrador (normalmente ya hecho al aprobar).
            if not p.body_md:
                logger.info("  sin borrador, generando ahora (red de seguridad)")
                if not generate_proposal_draft(db, p):
                    logger.error("  no se pudo generar body para propuesta %s", p.id)
                    continue

            # 2. Crear el Post copiando el borrador ya saneado/enlazado.
            slug = _unique_slug(db, _slugify(p.title))
            post = Post(
                slug=slug,
                kind=p.kind,
                status="draft",
                title=p.title[:240],
                excerpt=p.excerpt,
                body_md=p.body_md,
                meta_title=p.meta_title[:60] if p.meta_title else None,
                meta_description=p.meta_description[:155] if p.meta_description else None,
                target_keyword=p.target_keyword,
                target_keyword_slug=p.target_keyword_slug,
                content_key=p.content_key,
                source_url=p.source_url,
                source_name=p.source_name,
                hero_image_url=p.hero_image_url,
                hero_image_attribution=p.hero_image_attribution,
                hero_image_license=p.hero_image_license,
                hero_image_source_url=p.hero_image_source_url,
                entities=p.entities or [],
            )
            db.add(post)
            db.commit()
            db.refresh(post)

            # 3. Publicar (revalidate de Next; el email es el digest dominical).
            auto_publish_post(db, post)

            # 4. Marcar propuesta usada.
            p.status = "used"
            p.post_id = post.id
            db.commit()
            logger.info("  ✓ publicado como /blog/%s", slug)


if __name__ == "__main__":
    main()
