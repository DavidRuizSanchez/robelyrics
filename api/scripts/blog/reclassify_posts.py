"""Recalifica los posts publicados no-noticia: calcula y guarda engagement_score +
quality_tier. Con --regen-cornerstone / --regen-flagship, regenera al estándar
máximo los posts de ese tier, dejándolos en pending_review.

`--exclude-recent N` salta los N posts publicados MÁS RECIENTES en la regeneración
(p.ej. los que ya se regeneraron a mano hoy). Se recalifican igual, pero NO se
regeneran.

Uso:
  python -m scripts.blog.reclassify_posts                                  # informe
  python -m scripts.blog.reclassify_posts --regen-cornerstone
  python -m scripts.blog.reclassify_posts --regen-cornerstone --regen-flagship --exclude-recent 3
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
    ap.add_argument("--regen-flagship", action="store_true",
                    help="Regenera (a pending_review) también los posts flagship.")
    ap.add_argument("--exclude-recent", type=int, default=0, metavar="N",
                    help="Salta de la regeneración los N posts publicados más recientes.")
    args = ap.parse_args()

    db = SessionLocal()
    posts = db.query(Post).filter(Post.status == "published").order_by(Post.published_at.desc()).all()

    # Los N más recientes se recalifican pero NO se regeneran (p.ej. los de hoy).
    excluded_ids: set[int] = set()
    if args.exclude_recent > 0:
        recientes = posts[: args.exclude_recent]
        excluded_ids = {p.id for p in recientes}
        print("\nExcluidos de la regeneración (más recientes):")
        for p in recientes:
            print(f"  - {p.slug}  ({p.published_at:%Y-%m-%d})")

    # tier objetivo → recolectamos los posts a regenerar respetando la exclusión.
    regen_tiers = set()
    if args.regen_cornerstone:
        regen_tiers.add("cornerstone")
    if args.regen_flagship:
        regen_tiers.add("flagship")

    to_regen: list[tuple[Post, str | None, int | None, str]] = []
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
        skip = "  [excluido]" if p.id in excluded_ids else ""
        print(f"  {mark:14} score={score:3} src={src_t}/{src_i}{skip}  | {p.slug[:42]}")
        if tier in regen_tiers and p.id not in excluded_ids:
            to_regen.append((p, src_t, src_i, tier))

    n_corner = sum(1 for _, _, _, t in to_regen if t == "cornerstone")
    n_flag = sum(1 for _, _, _, t in to_regen if t == "flagship")
    print(f"\n→ A regenerar: {n_corner} cornerstone + {n_flag} flagship "
          f"(excluidos {len(excluded_ids)} recientes)")
    if to_regen:
        from scripts.blog.regen_entity_post import regen
        for p, st, si, tier in to_regen:
            print(f"\n=== Regenerando {tier}: {p.slug} ===")
            regen(db, p, kind=p.kind, source_type=st, source_id=si, apply=True, tier=tier)
    db.close()


if __name__ == "__main__":
    main()
