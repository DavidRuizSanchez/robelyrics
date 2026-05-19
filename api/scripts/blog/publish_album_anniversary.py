"""Publica aniversarios de lanzamiento de discos.

Diseñado para correr a diario en cron. Lee `albums.release_date` y, si hoy
coincide con el aniversario de algún disco, genera un post `kind='album-anniversary'`
con texto generado por `content_generator.generate_album_anniversary` e
imagen Wikimedia.

Como las efemérides personales, está exento del cap móvil de 2/semana: se
publica el día exacto del aniversario.

Idempotente por slug: `aniversario-disco-{slug}-{year}` donde {year} es el
año actual (de publicación), no el de lanzamiento. Permite que el mismo
disco genere una entrada al año.

Uso:
    python -m scripts.blog.publish_album_anniversary
    python -m scripts.blog.publish_album_anniversary --date 2026-06-22
    python -m scripts.blog.publish_album_anniversary --dry-run
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

from sqlalchemy import and_, extract, select

from app.db.models import Album, Artist, Post, Song
from app.db.session import SessionLocal
from app.services.content_generator import generate_album_anniversary
from app.services.publishing import schedule_or_publish
from app.services.wikimedia import search_image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _slug_for(album_slug: str, year: int) -> str:
    return f"aniversario-disco-{album_slug}-{year}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Sobrescribe la fecha (YYYY-MM-DD) para tests.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-image", action="store_true", help="Salta búsqueda Wikimedia."
    )
    args = parser.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()
    logger.info("Buscando aniversarios de discos para %s", today.isoformat())

    with SessionLocal() as db:
        # Discos cuya release_date cae en mes-día de hoy, con release_date < hoy
        # (es decir, ya se lanzaron — años_since >= 1).
        candidates = db.execute(
            select(Album, Artist)
            .join(Artist, Album.artist_id == Artist.id)
            .where(
                Album.release_date.isnot(None),
                extract("month", Album.release_date) == today.month,
                extract("day", Album.release_date) == today.day,
                Album.release_date < today,
            )
        ).all()

        if not candidates:
            logger.info("Sin aniversarios de discos hoy")
            return

        for album, artist in candidates:
            years = today.year - album.release_date.year
            slug = _slug_for(album.slug, today.year)

            existing = db.execute(
                select(Post).where(Post.slug == slug)
            ).scalar_one_or_none()
            if existing is not None:
                logger.info(
                    "Post %s ya existe (status=%s) — skip",
                    slug, existing.status,
                )
                continue

            # Tracklist (primeras canciones por número) como pista al LLM
            song_titles = [
                t for (t,) in db.execute(
                    select(Song.title)
                    .where(Song.album_id == album.id)
                    .order_by(Song.track_number.nulls_last())
                ).all()
            ]

            logger.info(
                "Generando aniversario para '%s' (%d años, %d tracks)",
                album.title, years, len(song_titles),
            )

            payload = generate_album_anniversary(
                album_title=album.title,
                artist_name=artist.name,
                years_since=years,
                release_year=album.release_date.year,
                track_titles=song_titles,
                today=today,
            )

            img = None
            if not args.no_image:
                img = search_image(f"{album.title} {artist.name}")
                if img is None:
                    img = search_image(artist.name)  # fallback
                if img:
                    logger.info(
                        "Imagen Wikimedia: %s (%s)",
                        img.source_page_url, img.license_short,
                    )

            if args.dry_run:
                print(f"\n=== DRY RUN — {album.title} ({years} años) ===")
                print("slug:", slug)
                print("title:", payload["title"])
                print("excerpt:", payload["excerpt"])
                print("---BODY---")
                print(payload["body_md"])
                print("=== END ===\n")
                continue

            body_md = payload["body_md"]
            hero_url = None
            attribution = None
            license_short = None
            source_url = None
            if img:
                body_md = body_md.rstrip() + "\n\n" + img.attribution_text + "\n"
                hero_url = img.thumb_url
                attribution = img.attribution_text
                license_short = img.license_short
                source_url = img.source_page_url
            elif album.cover_url:
                hero_url = album.cover_url

            post = Post(
                slug=slug,
                kind="album-anniversary",
                status="draft",
                title=payload["title"],
                excerpt=payload["excerpt"],
                body_md=body_md,
                meta_title=payload["meta_title"],
                meta_description=payload["meta_description"],
                anniversary_year=today.year,
                hero_image_url=hero_url,
                hero_image_attribution=attribution,
                hero_image_license=license_short,
                hero_image_source_url=source_url,
            )
            db.add(post)
            db.commit()
            db.refresh(post)

            result = schedule_or_publish(db, post)
            logger.info("Resultado publishing para %s: %s", slug, result)


if __name__ == "__main__":
    main()
