"""Genera un post tipo `spotlight` con análisis editorial de una canción.

Cron 1×/semana (martes 09:00 UTC). Selecciona una canción del catálogo que
NO haya sido spotlighted en los últimos 365 días, con rotación determinista
por week-of-year para reproducibilidad.

El cuerpo se genera con `content_generator.generate_song_spotlight` usando
el `seo_content.body_md` existente como contexto interno (no se cita
textualmente). Auto-publica vía `publishing.schedule_or_publish` (respeta
cap móvil de 2/semana).

Uso:
    python -m scripts.blog.publish_song_spotlight
    python -m scripts.blog.publish_song_spotlight --dry-run
    python -m scripts.blog.publish_song_spotlight --song-slug cipotecastico
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from sqlalchemy import select

from app.db.models import Album, Artist, Post, SeoContent, Song
from app.db.session import SessionLocal
from app.services.content_generator import generate_song_spotlight
from app.services.publishing import propose_for_review
from app.services.wikimedia import search_image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _spotlight_slug(song_slug: str, year: int, week: int) -> str:
    return f"cancion-de-la-semana-{song_slug}-{year}-w{week:02d}"


def _pick_song(db, today: date, override_slug: str | None) -> Song | None:
    if override_slug:
        row = db.execute(
            select(Song).where(Song.slug == override_slug)
        ).scalar_one_or_none()
        return row

    # Candidatas: canciones con seo_content publicado, no spotlighteadas en los
    # últimos 365 días.
    one_year_ago = today - timedelta(days=365)
    recent_spotlight_slugs = {
        row[0] for row in db.execute(
            select(Post.slug)
            .where(Post.kind == "spotlight")
            .where(Post.created_at >= one_year_ago)
        ).all()
    }

    rows = db.execute(
        select(Song)
        .join(SeoContent, (SeoContent.entity_type == "song") & (SeoContent.entity_id == Song.id))
        .where(SeoContent.published.is_(True))
        .order_by(Song.id)
    ).scalars().all()
    if not rows:
        return None

    # Rotación determinista: índice = (year * 53 + week) * primo mod n
    week = today.isocalendar().week
    idx = ((today.year * 53 + week) * 31) % len(rows)
    # Si la candidata ya tuvo spotlight reciente, avanza
    for offset in range(len(rows)):
        candidate = rows[(idx + offset) % len(rows)]
        slug = _spotlight_slug(candidate.slug, today.year, week)
        if slug not in recent_spotlight_slugs:
            return candidate
    return None  # no debería pasar pero defensivo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--song-slug", help="Fuerza una canción concreta.")
    parser.add_argument("--date", help="Sobrescribe la fecha (YYYY-MM-DD).")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-image", action="store_true")
    args = parser.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()
    week = today.isocalendar().week

    with SessionLocal() as db:
        song = _pick_song(db, today, args.song_slug)
        if song is None:
            logger.error("No hay candidata disponible")
            return

        # Carga album + artist
        album = db.get(Album, song.album_id)
        artist = db.get(Artist, album.artist_id) if album else None
        if album is None or artist is None:
            logger.error("Song %s sin album/artist relacionado", song.slug)
            return

        slug = _spotlight_slug(song.slug, today.year, week)
        existing = db.execute(
            select(Post).where(Post.slug == slug)
        ).scalar_one_or_none()
        if existing is not None:
            logger.info("Spotlight %s ya existe (status=%s), skip", slug, existing.status)
            return

        # Contexto: excerpt del seo_content de la canción
        seo = db.execute(
            select(SeoContent)
            .where(SeoContent.entity_type == "song", SeoContent.entity_id == song.id)
        ).scalar_one_or_none()
        seo_excerpt = (seo.body_md if seo else None)

        logger.info(
            "Spotlight semanal: '%s' (%s · %s)",
            song.title, album.title, artist.name,
        )
        payload = generate_song_spotlight(
            song_title=song.title,
            album_title=album.title,
            artist_name=artist.name,
            seo_excerpt=seo_excerpt,
            today=today,
        )

        # Imagen: cover del álbum o búsqueda Wikimedia
        hero_url = album.cover_url
        attribution = None
        license_short = None
        source_url = None
        if not args.no_image and not hero_url:
            img = search_image(f"{artist.name} {album.title}")
            if img:
                hero_url = img.thumb_url
                attribution = img.attribution_text
                license_short = img.license_short
                source_url = img.source_page_url

        body_md = payload["body_md"]
        if attribution:
            body_md = body_md.rstrip() + "\n\n" + attribution + "\n"

        if args.dry_run:
            print(f"\n=== DRY RUN — spotlight {song.title} ===")
            print("slug:", slug)
            print("title:", payload["title"])
            print("excerpt:", payload["excerpt"])
            print("---BODY---")
            print(body_md)
            return

        post = Post(
            slug=slug,
            kind="spotlight",
            status="draft",
            title=payload["title"],
            excerpt=payload["excerpt"],
            body_md=body_md,
            meta_title=payload["meta_title"],
            meta_description=payload["meta_description"],
            hero_image_url=hero_url,
            hero_image_attribution=attribution,
            hero_image_license=license_short,
            hero_image_source_url=source_url,
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        result = propose_for_review(db, post, notify=False)
        logger.info("Resultado: %s", result)


if __name__ == "__main__":
    main()
