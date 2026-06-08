"""Materializa las propuestas programadas: cuando llega su `scheduled_for`,
genera el body editorial (si falta), crea el `Post` y lo publica.

Cron diario. Para cada `ContentProposal` con status='scheduled' y
`scheduled_for <= hoy`:
  1. Si no tiene `body_md` (spotlight/evergreen/anniversary/album-anniversary),
     lo genera con `content_generator` según el `kind`.
  2. Busca imagen Wikimedia si no tiene.
  3. Crea el `Post` y lo publica vía `auto_publish_post` (que dispara
     newsletter on-publish + revalidate de Next).
  4. Marca la propuesta como `used` con `post_id`.

Las noticias (`kind='news'`) ya traen `body_md` del scraper: solo se crea
el Post.

Uso:
    python -m scripts.blog.materialize_proposals
    python -m scripts.blog.materialize_proposals --dry-run
"""
from __future__ import annotations

import argparse
import logging
import re
import unicodedata
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.db.models import (
    Album,
    Artist,
    Concept,
    ContentProposal,
    Place,
    Post,
    SeoContent,
    Song,
    Theme,
)
from app.db.session import SessionLocal
from app.services.content_generator import (
    generate_album_anniversary,
    generate_anniversary,
    generate_evergreen_topic,
    generate_seo_article,
    generate_song_spotlight,
)
from app.services.publishing import auto_publish_post
from app.services.wikimedia import search_image
from scripts.blog.context_builder import (
    album_context,
    artist_context,
    song_context,
    taxonomy_context,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROBE = "Robe Iniesta"


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


def _generate_body(db, p: ContentProposal) -> dict | None:
    """Genera el contenido editorial de una propuesta sin body, según kind.
    Devuelve dict con title/excerpt/body_md/meta_title/meta_description/entities
    o None si no se pudo."""
    today = date.today()

    if p.kind == "spotlight" and p.source_type == "song" and p.source_id:
        song = db.get(Song, p.source_id)
        if not song:
            return None
        album = db.get(Album, song.album_id)
        artist = db.get(Artist, album.artist_id) if album else None
        seo = db.execute(
            select(SeoContent).where(
                SeoContent.entity_type == "song", SeoContent.entity_id == song.id
            )
        ).scalar_one_or_none()
        try:
            ctx = song_context(db, song.id)
        except Exception:
            ctx = ""
        return generate_song_spotlight(
            song_title=song.title,
            album_title=album.title if album else "",
            artist_name=artist.name if artist else "",
            seo_excerpt=(seo.body_md if seo else None),
            context=ctx,
            today=today,
        )

    if p.kind == "album-anniversary" and p.source_type == "album" and p.source_id:
        album = db.get(Album, p.source_id)
        if not album:
            return None
        artist = db.get(Artist, album.artist_id)
        years = today.year - (album.release_date.year if album.release_date else today.year)
        track_titles = [
            t for (t,) in db.execute(
                select(Song.title).where(Song.album_id == album.id)
                .order_by(Song.track_number.nulls_last())
            ).all()
        ]
        try:
            ctx = album_context(db, album.id)
        except Exception:
            ctx = ""
        return generate_album_anniversary(
            album_title=album.title,
            artist_name=artist.name if artist else "",
            years_since=max(years, 1),
            release_year=album.release_date.year if album.release_date else album.year,
            track_titles=track_titles,
            context=ctx,
            today=today,
        )

    if p.kind == "anniversary":
        kind = "death" if p.source_type == "robe-death" else "birth"
        # años desde el evento
        if kind == "death":
            years = today.year - 2025
        else:
            years = today.year - 1962
        try:
            robe = db.execute(
                select(Artist).where(Artist.slug == "robe")
            ).scalar_one_or_none()
            ctx = artist_context(db, robe.id) if robe else ""
        except Exception:
            ctx = ""
        return generate_anniversary(
            kind, person_name=ROBE, years_since=max(years, 1),
            context=ctx, today=today,
        )

    if p.kind == "evergreen":
        # Propuesta SEO-driven (la fuente es keyword research, no taxonomía).
        if p.source_type == "seo":
            return generate_seo_article(
                title=p.title,
                angle=p.angle,
                keywords=p.keywords or [],
                today=today,
            )
        # Evergreen legacy de taxonomía (theme/place/concept).
        model = {"theme": Theme, "place": Place, "concept": Concept}.get(
            p.source_type or ""
        )
        if model and p.source_id:
            tax = db.get(model, p.source_id)
            if tax:
                try:
                    song_ids = [s.id for s in tax.songs]
                    seo_tax = db.execute(
                        select(SeoContent).where(
                            SeoContent.entity_type == p.source_type,
                            SeoContent.entity_id == tax.id,
                        )
                    ).scalar_one_or_none()
                    ctx = taxonomy_context(
                        db, song_ids, seo_tax.body_md if seo_tax else None
                    )
                except Exception:
                    ctx = ""
                return generate_evergreen_topic(
                    taxonomy_kind=p.source_type,
                    taxonomy_name=tax.name,
                    taxonomy_description=tax.description,
                    song_titles=[s.title for s in tax.songs],
                    context=ctx,
                    today=today,
                )
        return None

    return None


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

            # 1. Body: el de la propuesta (news) o generado
            if p.body_md:
                title = p.title
                excerpt = p.excerpt
                body_md = p.body_md
                meta_title = p.meta_title
                meta_description = p.meta_description
                entities = p.entities or []
                hero_url = p.hero_image_url
                hero_attr = p.hero_image_attribution
                hero_lic = p.hero_image_license
                hero_src = p.hero_image_source_url
            else:
                payload = _generate_body(db, p)
                if payload is None:
                    logger.error("  no se pudo generar body para propuesta %s", p.id)
                    continue
                title = payload["title"]
                excerpt = payload.get("excerpt")
                body_md = payload["body_md"]
                meta_title = payload.get("meta_title")
                meta_description = payload.get("meta_description")
                entities = payload.get("entities") or []
                hero_url = hero_attr = hero_lic = hero_src = None

            # Hero RELEVANTE: imagen de la entidad protagonista del post (su
            # foto curada). Overridea cualquier imagen previa de la propuesta
            # para garantizar que SIEMPRE es del sujeto del que se habla.
            from app.services.hero_image import pick_hero_image
            _img = pick_hero_image(db, entities)
            if _img:
                hero_url, hero_attr = _img["url"], _img["attribution"]
                hero_lic, hero_src = _img["license"], _img["source"]

            # Saneado anti marcas IA + jerarquía de headings + enlazado interno
            # automático a todo el corpus (máx. 4 enlaces más relevantes).
            from app.services.entity_resolver import (
                autolink_corpus,
                build_corpus_index,
                load_link_stats,
            )
            from app.services.text_sanitizer import (
                normalize_headings,
                strip_ai_tells,
            )
            body_md = strip_ai_tells(body_md) or body_md
            body_md = normalize_headings(body_md) or body_md
            body_md = autolink_corpus(
                body_md, build_corpus_index(db), max_links=4,
                link_stats=load_link_stats(),
            )

            # 2. Crear el Post
            slug = _unique_slug(db, _slugify(title))
            post = Post(
                slug=slug,
                kind=p.kind,
                status="draft",
                title=title[:240],
                excerpt=excerpt,
                body_md=body_md,
                meta_title=meta_title[:60] if meta_title else None,
                meta_description=meta_description[:155] if meta_description else None,
                target_keyword=p.target_keyword,
                target_keyword_slug=p.target_keyword_slug,
                source_url=p.source_url,
                source_name=p.source_name,
                hero_image_url=hero_url,
                hero_image_attribution=hero_attr,
                hero_image_license=hero_lic,
                hero_image_source_url=hero_src,
                entities=entities,
            )
            db.add(post)
            db.commit()
            db.refresh(post)

            # 3. Publicar (newsletter on-publish + revalidate)
            auto_publish_post(db, post)

            # 4. Marcar propuesta usada
            p.status = "used"
            p.post_id = post.id
            db.commit()
            logger.info("  ✓ publicado como /blog/%s", slug)


if __name__ == "__main__":
    main()
