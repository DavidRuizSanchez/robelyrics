"""Regenera un post de NOTICIA existente con el motor nuevo (artículo completo
de la fuente + voz de fan) y lo actualiza in situ. Reutilizable para la
regeneración de posts a la voz nueva.

Solo aplica a posts con `source_url` (noticias). Los demás (efemérides,
spotlights, evergreen) no tienen fuente externa y se regeneran por otra vía.

Uso:
  python -m scripts.blog.regen_one_post --slug <slug>
  python -m scripts.blog.regen_one_post --all-news
  python -m scripts.blog.regen_one_post --slug <slug> --dry-run
"""
from __future__ import annotations

import argparse
import logging

from app.db.models import Post
from app.db.session import SessionLocal
from app.services.article_extract import fetch_article_text
from app.services.content_generator import rewrite_news_editorial
from app.services.entity_resolver import (
    autolink_corpus,
    build_corpus_index,
    load_link_stats,
)
from app.services.text_sanitizer import normalize_headings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def regen_post_researched(db, post: Post, *, dry_run: bool) -> bool:
    """Modo NUEVO: investiga el tema (adaptado a su tipo) + escribe el post con
    máxima información, vídeo (+VideoObject) y foto reales, SIN acreditar al
    medio. Ver app.services.news_research."""
    from app.services.news_research import research_and_write
    from app.services.instagram import cloudinary_upload

    seed = ""
    if post.source_url:
        seed = fetch_article_text(post.source_url) or ""
    if not seed:
        seed = f"{post.title}\n\n{post.excerpt or ''}"

    out = research_and_write(
        db=db, headline=post.title, source_excerpt=seed, matched_term="Robe",
    )
    if not out.get("is_relevant", True) or not (out.get("body_md") or "").strip():
        logger.warning("  · %s: no relevante o sin cuerpo, se salta", post.slug)
        return False

    new_body = normalize_headings(out["body_md"]) or out["body_md"]
    new_body = autolink_corpus(
        new_body, build_corpus_index(db), max_links=4,
        exclude_slug=post.slug, link_stats=load_link_stats(),
    )
    video = out.get("video")
    img_url = out.get("image_url")
    logger.info(
        "  ✓ %s (%d chars) · vídeo=%s · foto=%s",
        post.slug, len(new_body), bool(video), bool(img_url),
    )
    if dry_run:
        print(f"\n===== {post.slug} =====")
        print("TÍTULO:", out["title"])
        print("VÍDEO:", video)
        print("FOTO:", img_url)
        print("---BODY---\n" + new_body[:2500])
        return True

    post.title = out["title"][:240]
    post.excerpt = (out.get("excerpt") or post.excerpt or "")[:200]
    post.body_md = new_body
    post.meta_title = (out.get("meta_title") or "")[:60]
    post.meta_description = (out.get("meta_description") or "")[:155]
    post.video = video
    # Sin acreditar al medio: la investigación es nuestra.
    post.source_name = None
    post.source_url = None
    if img_url:
        try:
            post.hero_image_url = cloudinary_upload.upload(
                img_url, folder="entreinteriores-art"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("  · %s: subida de foto falló (%s)", post.slug, exc)
    db.commit()
    return True


def regen_post(db, post: Post, *, dry_run: bool) -> bool:
    if not post.source_url:
        logger.info("  · %s sin source_url (no es noticia), se salta", post.slug)
        return False
    body = fetch_article_text(post.source_url) or ""
    if not body:
        logger.warning("  · %s: no se pudo leer la fuente, se salta", post.slug)
        return False
    out = rewrite_news_editorial(
        headline=post.title,
        source_excerpt=body,
        source_url=post.source_url,
        source_name=post.source_name or "la fuente",
        matched_term="Robe",
    )
    new_body = out.get("body_md") or ""
    if not new_body or len(new_body) < 400:
        logger.warning("  · %s: cuerpo regenerado demasiado corto, se salta", post.slug)
        return False
    new_body = normalize_headings(new_body) or new_body
    new_body = autolink_corpus(
        new_body, build_corpus_index(db), max_links=4,
        exclude_slug=post.slug, link_stats=load_link_stats(),
    )
    logger.info("  ✓ %s (%d chars)", post.slug, len(new_body))
    if dry_run:
        return True
    post.title = out["title"][:240]
    post.excerpt = (out.get("excerpt") or post.excerpt or "")[:200]
    post.body_md = new_body
    post.meta_title = (out.get("meta_title") or "")[:60]
    post.meta_description = (out.get("meta_description") or "")[:155]
    if out.get("entities"):
        post.entities = out["entities"]
    db.commit()
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug")
    ap.add_argument("--all-news", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--research", action="store_true",
        help="Modo nuevo: investiga el tema (web+corpus+vídeo+foto), sin acreditar al medio.",
    )
    args = ap.parse_args()

    with SessionLocal() as db:
        if args.slug:
            posts = db.query(Post).filter(Post.slug == args.slug).all()
        elif args.all_news:
            posts = (
                db.query(Post)
                .filter(Post.status == "published", Post.source_url.isnot(None))
                .all()
            )
        else:
            ap.error("indica --slug o --all-news")
            return
        n = 0
        for p in posts:
            fn = regen_post_researched if args.research else regen_post
            if fn(db, p, dry_run=args.dry_run):
                n += 1
        logger.info("Posts regenerados: %d/%d%s", n, len(posts),
                    " (dry-run)" if args.dry_run else "")


if __name__ == "__main__":
    main()
