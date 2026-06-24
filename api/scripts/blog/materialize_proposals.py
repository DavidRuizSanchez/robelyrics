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
from app.services.fact_check import check_body, correct_body
from app.services.publishing import auto_publish_post, propose_for_review

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

            # 3. GATE FACTUAL antes de publicar. Auto-corrige las contradicciones
            #    canónicas de BD (canción↔álbum↔año); si la verificación web
            #    detecta algo dudoso (to_review), el post NO se auto-publica: va a
            #    revisión humana. Solo lo que pasa LIMPIO se publica solo.
            report = check_body(db, post.body_md, use_web=True)
            skipped: list = []
            if report.autofixes:
                fixed, skipped = correct_body(db, post.body_md, report)
                if fixed and fixed != post.body_md:
                    post.body_md = fixed
                    db.commit()
                    db.refresh(post)
                    logger.info("  fact-check: %d hecho(s) corregido(s) contra BD",
                                len(report.autofixes) - len(skipped))

            # A revisión humana si la web detecta algo dudoso (to_review) o si
            # algún hecho refutado no se pudo corregir limpio (skipped → reformular).
            needs_review = report.to_review + skipped
            if needs_review:
                for v in needs_review:
                    logger.info("  fact-check REVISAR: %s · %s", v.claim.type, v.claim.subject)
                propose_for_review(db, post)
                p.status = "used"
                p.post_id = post.id
                db.commit()
                logger.info("  ⚠ a revisión humana (%d dato(s)): /blog/%s",
                            len(needs_review), slug)
                continue

            # 4. Limpio → publicar (revalidate de Next; el email es el digest dominical).
            #    factcheck=False: el gate de arriba ya verificó (con capa web).
            auto_publish_post(db, post, factcheck=False)
            p.status = "used"
            p.post_id = post.id
            db.commit()
            logger.info("  ✓ publicado como /blog/%s", slug)


if __name__ == "__main__":
    main()
