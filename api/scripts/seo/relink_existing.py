"""Retroactivo: re-aplica jerarquía de headings (H1→H2→H3) + enlazado interno
automático al corpus (máx. 4 enlaces relevantes) a TODO el contenido ya
publicado: posts del blog + seo_content.

Parte de cero (quita los enlaces previos) para que el ranking de relevancia
elija los 4 mejores limpios. Idempotente. Uso:

    python -m scripts.seo.relink_existing --dry-run
    python -m scripts.seo.relink_existing            (aplica)
    python -m scripts.seo.relink_existing --revalidate  (aplica + refresca Next)
"""
from __future__ import annotations

import argparse
import logging
import re

from app.db.models import Post, SeoContent
from app.db.session import SessionLocal
from app.services.entity_resolver import (
    autolink_corpus,
    build_corpus_index,
    load_link_stats,
)
from app.services.text_sanitizer import normalize_headings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Enlace markdown inline (no imágenes: lookbehind para '!').
_LINK = re.compile(r"(?<!\!)\[([^\]]+)\]\([^)]+\)")


def _clean(md, index, stats, *, exclude_slug=None):
    if not md:
        return md
    out = _LINK.sub(r"\1", md)                       # quita enlaces previos
    out = normalize_headings(out) or out             # H1→H2→H3
    out = autolink_corpus(
        out, index, max_links=4, exclude_slug=exclude_slug, link_stats=stats
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--revalidate", action="store_true",
                    help="Tras aplicar, pide a Next que revalide los posts.")
    args = ap.parse_args()

    with SessionLocal() as db:
        index = build_corpus_index(db)
        stats = load_link_stats()
        logger.info("Índice de corpus: %d entidades · stats de enlaces: %d",
                    len(index), len(stats))

        posts = db.query(Post).filter(Post.body_md.isnot(None)).all()
        changed_posts: list[str] = []
        for p in posts:
            new = _clean(p.body_md, index, stats)
            if new != p.body_md:
                changed_posts.append(p.slug)
                if not args.dry_run:
                    p.body_md = new

        secs = db.query(SeoContent).filter(SeoContent.body_md.isnot(None)).all()
        changed_secs = 0
        for s in secs:
            new = _clean(s.body_md, index, stats, exclude_slug=s.slug)
            if new != s.body_md:
                changed_secs += 1
                if not args.dry_run:
                    s.body_md = new

        if not args.dry_run:
            db.commit()
        logger.info("Posts cambiados: %d/%d · seo_content cambiados: %d/%d",
                    len(changed_posts), len(posts), changed_secs, len(secs))
        for slug in changed_posts:
            logger.info("  post: %s", slug)

        if args.revalidate and not args.dry_run:
            from app.services.publishing import _revalidate_next
            for slug in changed_posts:
                _revalidate_next(slug)
            logger.info("Revalidate de Next disparado para %d posts", len(changed_posts))


if __name__ == "__main__":
    main()
