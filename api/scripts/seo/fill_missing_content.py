"""Rellena las fichas SEO que falten (entidades en BD sin contenido publicado).

Nace del alta automática de discos: cuando el Motor de Consenso da de alta un
disco ausente, el catálogo pasa a tener un álbum y sus canciones al instante,
pero sus páginas darían 404 (`/[artist]/[album]` hace notFound sin `seo_body`)
mientras el listado de discografía YA las enlaza. Enlace roto en producción.

Generar cada ficha con el motor profundo cuesta ~2 minutos, así que no cabe en un
request HTTP: el alta lo lanza desatendido y esto lo hace por lotes. En el cron
corre en modo `--missing` como red de seguridad, por si el alta se cortó a medias.

Uso:
  python -m scripts.seo.fill_missing_content --album-slug tu-en-tu-casa-...
  python -m scripts.seo.fill_missing_content --missing --limit 10
  python -m scripts.seo.fill_missing_content --missing --dry-run
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys

from sqlalchemy import select

from app.db.models import Album, SeoContent, Song
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Lotes pequeños: cada ficha tarda ~2 min y así un fallo no tira todo el trabajo.
BATCH = 4


def _covered(db, entity_type: str) -> set[int]:
    """Ids que YA tienen ficha publicada."""
    return set(db.execute(
        select(SeoContent.entity_id).where(
            SeoContent.entity_type == entity_type,
            SeoContent.published.is_(True),
        )
    ).scalars())


def missing_for_album(db, album_slug: str) -> dict[str, list[str]]:
    """Slugs sin ficha del álbum y de sus canciones."""
    album = db.execute(select(Album).where(Album.slug == album_slug)).scalar_one_or_none()
    if album is None:
        logger.error("No existe el álbum %s", album_slug)
        return {}
    out: dict[str, list[str]] = {}
    if album.id not in _covered(db, "album"):
        out["album"] = [album.slug]
    song_done = _covered(db, "song")
    songs = db.execute(select(Song).where(Song.album_id == album.id)).scalars().all()
    pend = [s.slug for s in songs if s.id not in song_done]
    if pend:
        out["song"] = pend
    return out


def missing_everywhere(db, limit: int | None = None) -> dict[str, list[str]]:
    """Barrido general: álbumes y canciones sin ficha publicada."""
    out: dict[str, list[str]] = {}
    alb_done = _covered(db, "album")
    albums = [a.slug for a in db.execute(select(Album)).scalars() if a.id not in alb_done]
    if albums:
        out["album"] = albums
    song_done = _covered(db, "song")
    songs = [s.slug for s in db.execute(select(Song)).scalars() if s.id not in song_done]
    if songs:
        out["song"] = songs
    if limit:
        # El álbum manda: su ficha es la que enlaza el listado de discografía.
        room = limit
        capped: dict[str, list[str]] = {}
        for et in ("album", "song"):
            if room <= 0 or et not in out:
                continue
            capped[et] = out[et][:room]
            room -= len(capped[et])
        dropped = sum(len(v) for v in out.values()) - sum(len(v) for v in capped.values())
        if dropped:
            logger.info("Tope de %d: quedan %d ficha(s) para la próxima pasada.", limit, dropped)
        return capped
    return out


def generate(entity_type: str, slugs: list[str], *, dry_run: bool = False) -> int:
    """Genera las fichas por lotes con el motor profundo. Devuelve nº de fallos."""
    failures = 0
    for i in range(0, len(slugs), BATCH):
        batch = slugs[i:i + BATCH]
        cmd = [
            sys.executable, "-m", "scripts.seo.regenerate_deep",
            "--entity-type", entity_type, "--slugs", ",".join(batch), "--publish",
        ]
        logger.info("[%s] generando %d ficha(s): %s", entity_type, len(batch), ", ".join(batch))
        if dry_run:
            continue
        res = subprocess.run(cmd, check=False)
        if res.returncode != 0:
            failures += 1
            logger.error("[%s] lote falló (código %s): %s", entity_type, res.returncode, batch)
    return failures


def main() -> None:
    ap = argparse.ArgumentParser(description="Rellena fichas SEO ausentes.")
    ap.add_argument("--album-slug", help="solo este álbum y sus canciones")
    ap.add_argument("--missing", action="store_true", help="barre todas las entidades sin ficha")
    ap.add_argument("--limit", type=int, default=None, help="tope de fichas por pasada")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not (args.album_slug or args.missing):
        ap.error("usa --album-slug SLUG o --missing")

    db = SessionLocal()
    try:
        pend = (missing_for_album(db, args.album_slug) if args.album_slug
                else missing_everywhere(db, args.limit))
    finally:
        db.close()

    total = sum(len(v) for v in pend.values())
    if not total:
        logger.info("Nada que rellenar: todas las fichas están publicadas.")
        return

    logger.info("Fichas por generar: %s (≈%d min)",
                {k: len(v) for k, v in pend.items()}, total * 2)
    failures = 0
    for entity_type in ("album", "song"):  # el álbum primero: es lo que se enlaza
        if entity_type in pend:
            failures += generate(entity_type, pend[entity_type], dry_run=args.dry_run)
    if failures:
        logger.warning("Terminado con %d lote(s) fallido(s); la red de seguridad "
                       "del cron lo reintentará.", failures)
    else:
        logger.info("Fichas al día.")


if __name__ == "__main__":
    main()
