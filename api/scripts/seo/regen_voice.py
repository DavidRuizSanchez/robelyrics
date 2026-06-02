"""Regenera el contenido SEO a la voz nueva (1ª persona) + profundidad, disco
a disco, REPUBLICANDO cada álbum al terminar. Así el sitio nunca queda a
oscuras entero: solo el disco en curso está unos minutos en borrador.

Orden: canciones+disco de cada álbum (con destilado + voz), luego artistas.

Uso:
  python -m scripts.seo.regen_voice                  # todo (canciones, discos, artistas)
  python -m scripts.seo.regen_voice --albums agila   # solo estos álbumes
  python -m scripts.seo.regen_voice --skip-artists
"""
from __future__ import annotations

import argparse

from openai import OpenAI
from sqlalchemy import text

from app.config import get_settings
from app.db.models import Album, Artist
from scripts.research.common import get_session, log
from scripts.seo.generate_album_content import generate_for_album
from scripts.seo.generate_artist_content import generate_for_artist
from scripts.seo.generate_song_content import generate_for_song


def _republish_album(db, album_slug: str) -> None:
    db.execute(text(
        "UPDATE seo_content sc SET published=true, reviewed_at=now() "
        "FROM songs s JOIN albums a ON a.id=s.album_id "
        "WHERE sc.entity_type='song' AND sc.entity_id=s.id AND a.slug=:slug"
    ), {"slug": album_slug})
    db.execute(text(
        "UPDATE seo_content SET published=true, reviewed_at=now() "
        "WHERE entity_type='album' AND slug=:slug"
    ), {"slug": album_slug})
    db.commit()


def _republish_artist(db, artist_slug: str) -> None:
    db.execute(text(
        "UPDATE seo_content SET published=true, reviewed_at=now() "
        "WHERE entity_type='artist' AND slug=:slug"
    ), {"slug": artist_slug})
    db.commit()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--albums", nargs="*", help="Solo estos slugs de álbum.")
    ap.add_argument("--skip-artists", action="store_true")
    args = ap.parse_args()

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return
    client = OpenAI(api_key=settings.openai_api_key)

    with get_session() as db:
        q = db.query(Album).order_by(Album.id)
        album_slugs = [a.slug for a in q.all()]
        artist_slugs = [a.slug for a in db.query(Artist).order_by(Artist.id).all()]
    if args.albums:
        album_slugs = [s for s in album_slugs if s in set(args.albums)]

    log(f"REGEN VOZ: {len(album_slugs)} álbumes" +
        ("" if args.skip_artists else f" + {len(artist_slugs)} artistas"))

    for ai, slug in enumerate(album_slugs, 1):
        with get_session() as db:
            album = db.query(Album).filter(Album.slug == slug).first()
            song_slugs = [s.slug for s in album.songs]
            aname = album.artist.name
        log(f"[{ai}/{len(album_slugs)}] {aname} · {slug} ({len(song_slugs)} canciones)")
        for ss in song_slugs:
            with get_session() as db:
                try:
                    generate_for_song(client, db, ss, force=True)
                except Exception as e:  # noqa: BLE001
                    log(f"  fallo canción {ss}: {e}", "err")
        with get_session() as db:
            try:
                generate_for_album(client, db, slug, force=True)
            except Exception as e:  # noqa: BLE001
                log(f"  fallo álbum {slug}: {e}", "err")
        with get_session() as db:
            _republish_album(db, slug)
        log(f"  ✓ {slug} regenerado y republicado", "ok")

    if not args.skip_artists:
        for slug in artist_slugs:
            with get_session() as db:
                try:
                    generate_for_artist(client, db, slug, force=True)
                except Exception as e:  # noqa: BLE001
                    log(f"  fallo artista {slug}: {e}", "err")
            with get_session() as db:
                _republish_artist(db, slug)
            log(f"  ✓ artista {slug} regenerado y republicado", "ok")

    log("REGEN VOZ completado", "ok")


if __name__ == "__main__":
    main()
