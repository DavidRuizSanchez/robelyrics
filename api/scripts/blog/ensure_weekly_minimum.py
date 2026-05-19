"""Garantiza el mínimo de 2 posts/semana.

Cron diario 11:00 UTC (después de scraper y flush_scheduled_due). Mira los
publicados de los últimos 7 días. Si hay `< 2`, dispara un spotlight ad-hoc
para llenar el hueco. Si ya hubo spotlight reciente, hace fallback a un
post evergreen sobre una taxonomía rotativa.

Importante: las efemérides (kind anniversary y album-anniversary) NO cuentan
para el mínimo porque son fechadas y ya cubren sus días. El mínimo es de
contenido editorial regular.

Uso:
    python -m scripts.blog.ensure_weekly_minimum
    python -m scripts.blog.ensure_weekly_minimum --dry-run
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, func

from app.db.models import Concept, Place, Post, Song, SongConcept, SongPlace, SongTheme, Theme
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MIN_PER_WEEK = 2
WINDOW_DAYS = 7

CAP_EXEMPT = {"anniversary", "album-anniversary"}


def _published_last_7d(db) -> int:
    seven_ago = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    return db.execute(
        select(func.count(Post.id))
        .where(Post.status == "published")
        .where(Post.published_at >= seven_ago)
        .where(~Post.kind.in_(CAP_EXEMPT))
    ).scalar_one()


def _had_spotlight_recently(db, *, days: int = 5) -> bool:
    threshold = datetime.now(timezone.utc) - timedelta(days=days)
    return (
        db.execute(
            select(func.count(Post.id))
            .where(Post.kind == "spotlight")
            .where(Post.created_at >= threshold)
        ).scalar_one()
        > 0
    )


def _trigger_spotlight(dry_run: bool) -> None:
    """Lanza un spotlight ad-hoc importando el módulo y reutilizando su main."""
    from scripts.blog.publish_song_spotlight import _pick_song, _spotlight_slug
    from app.services.content_generator import generate_song_spotlight
    from app.services.publishing import propose_for_review
    from app.services.wikimedia import search_image
    from app.db.models import Album, Artist, Post as PostModel, SeoContent

    today = date.today()
    week = today.isocalendar().week
    with SessionLocal() as db:
        song = _pick_song(db, today, override_slug=None)
        if not song:
            logger.error("ensure_weekly_minimum: sin candidata para spotlight")
            return
        album = db.get(Album, song.album_id)
        artist = db.get(Artist, album.artist_id)
        slug = _spotlight_slug(song.slug, today.year, week)
        existing = db.execute(
            select(PostModel).where(PostModel.slug == slug)
        ).scalar_one_or_none()
        if existing is not None:
            logger.info("Spotlight %s ya existe — skip", slug)
            return
        seo = db.execute(
            select(SeoContent).where(
                SeoContent.entity_type == "song",
                SeoContent.entity_id == song.id,
            )
        ).scalar_one_or_none()
        payload = generate_song_spotlight(
            song_title=song.title,
            album_title=album.title,
            artist_name=artist.name,
            seo_excerpt=(seo.body_md if seo else None),
            today=today,
        )
        body_md = payload["body_md"]
        hero_url = album.cover_url
        if not hero_url:
            img = search_image(f"{artist.name} {album.title}")
            if img:
                hero_url = img.thumb_url
                body_md = body_md.rstrip() + "\n\n" + img.attribution_text + "\n"

        if dry_run:
            print(f"[dry-run] spotlight: {payload['title']}")
            return

        post = PostModel(
            slug=slug,
            kind="spotlight",
            status="draft",
            title=payload["title"],
            excerpt=payload["excerpt"],
            body_md=body_md,
            meta_title=payload["meta_title"],
            meta_description=payload["meta_description"],
            hero_image_url=hero_url,
            entities=payload.get("entities") or [],
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        propose_for_review(db, post, notify=False)
        logger.info("Spotlight ad-hoc creado para llenar el cap semanal")


def _trigger_evergreen(dry_run: bool) -> None:
    """Pieza evergreen sobre una taxonomía rotativa."""
    from app.services.content_generator import generate_evergreen_topic
    from app.services.publishing import propose_for_review

    today = date.today()
    week = today.isocalendar().week

    with SessionLocal() as db:
        # Rotación entre tipos por semana: 0→theme, 1→place, 2→concept
        kind_idx = week % 3
        model_map = [
            ("tema", Theme, SongTheme, SongTheme.theme_id),
            ("lugar", Place, SongPlace, SongPlace.place_id),
            ("concepto", Concept, SongConcept, SongConcept.concept_id),
        ]
        kind_label, Model, Join, fk = model_map[kind_idx]

        # Toma una taxonomía determinista por week
        rows = db.execute(select(Model).order_by(Model.id)).scalars().all()
        if not rows:
            logger.warning("No hay %ss en DB", kind_label)
            return
        item = rows[(today.year * 53 + week) % len(rows)]

        # Canciones donde aparece
        song_titles = [
            t for (t,) in db.execute(
                select(Song.title).join(Join, Song.id == Join.song_id).where(fk == item.id)
            ).all()
        ]
        if not song_titles:
            logger.warning("%s %r sin canciones — busco otro", kind_label, item.slug)
            # busca el primero que tenga canciones
            for r in rows:
                titles = [
                    t for (t,) in db.execute(
                        select(Song.title).join(Join, Song.id == Join.song_id).where(fk == r.id)
                    ).all()
                ]
                if titles:
                    item = r
                    song_titles = titles
                    break
            if not song_titles:
                logger.error("Sin %ss con canciones asociadas — abort", kind_label)
                return

        slug = f"evergreen-{kind_label}-{item.slug}-{today.year}-w{week:02d}"
        existing = db.execute(
            select(Post).where(Post.slug == slug)
        ).scalar_one_or_none()
        if existing is not None:
            logger.info("Evergreen %s ya existe — skip", slug)
            return

        payload = generate_evergreen_topic(
            taxonomy_kind=kind_label,
            taxonomy_name=item.name,
            taxonomy_description=item.description,
            song_titles=song_titles,
            today=today,
        )

        if dry_run:
            print(f"[dry-run] evergreen ({kind_label} {item.slug}): {payload['title']}")
            return

        post = Post(
            slug=slug,
            kind="evergreen",
            status="draft",
            title=payload["title"],
            excerpt=payload["excerpt"],
            body_md=payload["body_md"],
            meta_title=payload["meta_title"],
            meta_description=payload["meta_description"],
            entities=payload.get("entities") or [],
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        propose_for_review(db, post, notify=False)
        logger.info("Evergreen creado para %s %r", kind_label, item.slug)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force-evergreen",
        action="store_true",
        help="Salta spotlight y va directo a evergreen (útil para test).",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        count = _published_last_7d(db)
    logger.info(
        "Publicados últimos 7d (sin aniversarios): %d / mínimo %d",
        count, MIN_PER_WEEK,
    )

    # Generamos contenido nuevo solo si faltan posts publicados (no para
    # mantener la cola de pending alta — el user decide qué publicar).
    if count < MIN_PER_WEEK:
        needed = MIN_PER_WEEK - count
        logger.info("Faltan %d post(s) publicados — disparando fallback", needed)
        with SessionLocal() as db:
            had_recent = (
                _had_spotlight_recently(db) if not args.force_evergreen else True
            )
        for _ in range(needed):
            if not had_recent:
                _trigger_spotlight(args.dry_run)
                had_recent = True
            else:
                _trigger_evergreen(args.dry_run)
    else:
        logger.info("Mínimo semanal cubierto, no genero nuevos contenidos")

    # SIEMPRE: si hay pendings sin revisar, manda email consolidado al admin
    # (1 email/día). Idempotente respecto al contenido del mail.
    if not args.dry_run:
        from app.services.publishing import _notify_admin_review
        with SessionLocal() as db:
            latest = (
                db.query(Post)
                .filter(Post.status == "pending_review")
                .order_by(Post.created_at.desc())
                .first()
            )
            if latest is not None:
                _notify_admin_review(db, latest)
                logger.info("Email consolidado enviado al admin")
            else:
                logger.info("Sin pendings, no envío email")


if __name__ == "__main__":
    main()
