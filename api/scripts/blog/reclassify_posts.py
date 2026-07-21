"""Recalifica los posts publicados no-noticia: calcula y guarda engagement_score +
quality_tier. Con --regen-cornerstone, regenera al estándar máximo SOLO los que
salen cornerstone (temáticas de alto engagement), dejándolos en pending_review.

Uso:
  python -m scripts.blog.reclassify_posts                 # solo clasifica (informe)
  python -m scripts.blog.reclassify_posts --regen-cornerstone
"""
from __future__ import annotations

import argparse
import logging

from app.db.models import ContentProposal, Post
from app.db.session import SessionLocal
from app.services.engagement import compute_for_proposal, content_tier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class _Shim:
    """Objeto mínimo para compute_for_proposal cuando el post no tiene propuesta."""
    def __init__(self, entities, source_type, source_id):
        self.entities = entities
        self.search_volume = None
        self.source_type = source_type
        self.source_id = source_id


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--regen-cornerstone", action="store_true",
                    help="Regenera (a pending_review) los posts que salgan cornerstone.")
    args = ap.parse_args()

    db = SessionLocal()
    posts = db.query(Post).filter(Post.status == "published").order_by(Post.published_at.desc()).all()
    cornerstones: list[tuple[Post, str | None, int | None]] = []
    print(f"\nRecalificando {len(posts)} posts publicados (noticias excluidas):\n")
    for p in posts:
        if p.kind == "news":
            print(f"  (noticia, excluida)                          | {p.slug[:44]}")
            continue
        prop = db.query(ContentProposal).filter(ContentProposal.post_id == p.id).first()
        src_t = prop.source_type if prop else None
        src_i = prop.source_id if prop else None
        obj = prop if prop else _Shim(p.entities, src_t, src_i)
        score, base = compute_for_proposal(db, obj)
        tier = content_tier(p.kind, score, base, src_t)
        p.engagement_score = score
        p.quality_tier = tier
        db.commit()
        mark = "★ CORNERSTONE" if tier == "cornerstone" else f"  {tier}"
        print(f"  {mark:14} score={score:3} src={src_t}/{src_i}  | {p.slug[:42]}")
        if tier == "cornerstone":
            cornerstones.append((p, src_t, src_i))

    print(f"\n→ Cornerstones detectados: {len(cornerstones)}")
    if args.regen_cornerstone and cornerstones:
        from scripts.blog.regen_entity_post import regen
        for p, st, si in cornerstones:
            print(f"\n=== Regenerando cornerstone: {p.slug} ===")
            regen(db, p, kind=p.kind, source_type=st, source_id=si, apply=True, tier="cornerstone")
    db.close()


if __name__ == "__main__":
    main()
