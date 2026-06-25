"""Regenera con el MOTOR PROFUNDO el contenido que el rigor descartó/despublicó,
para revivir lo que tiene material real (canciones, discos, Robe, temas) en vez
de dejarlo muerto. Lo que aun así no llegue al listón, se queda fuera.

Solo tipos ANCLADOS a una entidad real (tienen de dónde sacar sustancia):
spotlight (canción), album-anniversary (disco), anniversary (Robe), evergreen de
taxonomía (theme/place/concept). Las noticias/tributos flacos NO se regeneran:
no hay material y volverían a caer.

Modos:
  (def)     propuestas DESCARTADAS ancladas → regen deep → rigor → si pasa,
            vuelven al banco como 'proposed'.
  --posts   posts en 'pending_review' (despublicados) cuya propuesta origen está
            anclada → regen deep → rigor → si pasa, se REPUBLICAN.

SIEMPRE probar con --dry-run primero.

Uso:
    python -m scripts.blog.regenerate_rejected --dry-run
    python -m scripts.blog.regenerate_rejected
    python -m scripts.blog.regenerate_rejected --posts --dry-run
    python -m scripts.blog.regenerate_rejected --posts
"""
from __future__ import annotations

import argparse
import logging

from app.db.models import ContentProposal, Post
from app.db.session import SessionLocal
from app.services.draft_generator import generate_body, generate_proposal_draft
from app.services.editorial_review import review as editorial_review

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Tipos con entidad real detrás (regenerables con sustancia).
ANCHORED = {"spotlight", "album-anniversary", "anniversary", "evergreen"}


def _is_anchored(kind: str, source_type: str | None, source_id: int | None) -> bool:
    if kind in ("spotlight", "album-anniversary", "anniversary"):
        return True
    if kind == "evergreen" and source_type in ("theme", "place", "concept") and source_id:
        return True
    return False


def _regen_proposals(db, args) -> None:
    stats = {"intentadas": 0, "revividas": 0, "siguen_fuera": 0}
    q = db.query(ContentProposal).filter(ContentProposal.status == "discarded")
    if args.ids:
        q = q.filter(ContentProposal.id.in_(args.ids))
    props = [p for p in q.order_by(ContentProposal.id).all()
             if _is_anchored(p.kind, p.source_type, p.source_id)]
    logger.info("Propuestas descartadas y ANCLADAS a regenerar: %d", len(props))

    for p in props:
        stats["intentadas"] += 1
        logger.info("[#%s] (%s) %s", p.id, p.kind, p.title)
        if args.dry_run:
            continue
        p.body_md = None  # fuerza regeneración por el motor profundo
        if not generate_proposal_draft(db, p):
            logger.info("  no se pudo regenerar")
            stats["siguen_fuera"] += 1
            continue
        v = editorial_review(p.body_md, kind=p.kind,
                             subject=(p.target_keyword or p.title or "").strip())
        if v.verdict == "reject":
            stats["siguen_fuera"] += 1
            logger.info("  sigue sin llegar (score %d) → queda descartada", v.score)
            continue
        if v.verdict == "revise" and v.tightened_body_md:
            p.body_md = v.tightened_body_md
        p.status = "proposed"
        db.commit()
        stats["revividas"] += 1
        logger.info("  ✓ revivida (score %d) → vuelve al banco como 'proposed'", v.score)

    logger.info("Regeneración propuestas %s: %d intentadas · %d revividas · %d siguen fuera",
                "[DRY-RUN]" if args.dry_run else "aplicada",
                stats["intentadas"], stats["revividas"], stats["siguen_fuera"])


def _regen_posts(db, args) -> None:
    stats = {"intentados": 0, "republicados": 0, "siguen_fuera": 0}
    q = db.query(Post).filter(Post.status == "pending_review")
    if args.ids:
        q = q.filter(Post.id.in_(args.ids))
    posts = q.order_by(Post.id).all()
    logger.info("Posts en revisión a intentar revivir: %d", len(posts))

    for post in posts:
        prop = (
            db.query(ContentProposal)
            .filter(ContentProposal.post_id == post.id)
            .first()
        )
        if not prop or not _is_anchored(prop.kind, prop.source_type, prop.source_id):
            continue
        stats["intentados"] += 1
        logger.info("[post #%s] (%s) %s", post.id, post.kind, post.title)
        if args.dry_run:
            continue
        # generate_body parte del cuerpo de la propuesta; lo limpiamos para forzar
        # la regeneración con el motor profundo.
        prop.body_md = None
        payload = generate_body(db, prop)
        if not payload or not payload.get("body_md"):
            stats["siguen_fuera"] += 1
            logger.info("  no se pudo regenerar")
            continue
        body = payload["body_md"]
        v = editorial_review(body, kind=post.kind,
                             subject=(post.target_keyword or post.title or "").strip())
        if v.verdict == "reject":
            stats["siguen_fuera"] += 1
            logger.info("  sigue sin llegar (score %d) → queda en revisión", v.score)
            continue
        if v.verdict == "revise" and v.tightened_body_md:
            body = v.tightened_body_md
        post.body_md = body
        post.title = (payload.get("title") or post.title)[:240]
        post.excerpt = payload.get("excerpt") or post.excerpt
        from app.services.publishing import auto_publish_post
        auto_publish_post(db, post, factcheck=False, rigor=False)
        stats["republicados"] += 1
        logger.info("  ✓ republicado (score %d): /blog/%s", v.score, post.slug)

    logger.info("Regeneración posts %s: %d intentados · %d republicados · %d siguen fuera",
                "[DRY-RUN]" if args.dry_run else "aplicada",
                stats["intentados"], stats["republicados"], stats["siguen_fuera"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--posts", action="store_true", help="revivir posts despublicados")
    parser.add_argument("--ids", type=int, nargs="*")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.posts:
            _regen_posts(db, args)
        else:
            _regen_proposals(db, args)


if __name__ == "__main__":
    main()
