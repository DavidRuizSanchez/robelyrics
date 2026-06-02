"""Ingesta de respaldo cuando Genius está caído/bloqueado (Cloudflare).

Fuentes abiertas, sin scraping ni evasión:
  - Tracklist desde **MusicBrainz** (release del álbum).
  - Letras desde **LRCLIB** (lyrics abiertas).

Reutiliza `upsert_song_with_lyrics` de scripts.ingest (mismo modelo de
lines/chunks/tsv). El álbum y el artista deben existir ya (seed_catalog).

Uso:
  python -m scripts.ingest_lrclib --artist extremoduro --album-slug pedra
  python -m scripts.ingest_lrclib --artist extremoduro --album-slug pedra --dry-run
"""
from __future__ import annotations

import argparse
import logging
import re
import time

import httpx

from app.db.models import Album, Artist
from app.db.session import SessionLocal
from scripts.ingest import upsert_song_with_lyrics
from scripts.sources.genius import FetchedTrack

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_UA = {"User-Agent": "RobeLyrics/1.0 (https://entreinteriores.com; davidruizsanchez@gmail.com)"}
_MB = "https://musicbrainz.org/ws/2"
_LRC = "https://lrclib.net/api"


def _norm(s: str) -> str:
    s = re.sub(r"[\(\[].*?[\)\]]", "", s or "")
    s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip().lower()


def mb_tracklist(http: httpx.Client, album_title: str, artist_name: str,
                 year: int | None = None) -> list[str]:
    """Tracklist desde MusicBrainz. Si se da `year`, restringe a releases de ese
    año (evita recopilaciones homónimas mal etiquetadas); entre las candidatas
    elige la de título EXACTO y, a igualdad, la de más pistas."""
    q = f'release:"{album_title}" AND artist:"{artist_name}"'
    r = http.get(f"{_MB}/release/", params={"query": q, "fmt": "json", "limit": 25})
    r.raise_for_status()
    releases = r.json().get("releases", [])
    want = _norm(album_title)
    # Título exacto (normalizado) para no arrastrar recopilaciones que solo
    # contienen el nombre del álbum.
    releases = [x for x in releases if _norm(x.get("title", "")) == want] or releases
    if year:
        same_year = [x for x in releases if str(x.get("date", "")).startswith(str(year))]
        if same_year:
            releases = same_year
    if not releases:
        return []
    best = max(releases, key=lambda x: x.get("track-count", 0) or 0)
    time.sleep(1.1)  # rate-limit MusicBrainz
    rr = http.get(f"{_MB}/release/{best['id']}", params={"inc": "recordings", "fmt": "json"})
    rr.raise_for_status()
    titles = [t["title"] for m in rr.json().get("media", []) for t in m.get("tracks", [])]
    logger.info("MusicBrainz: release «%s» (%s) → %d pistas",
                best.get("title"), best.get("date", "?"), len(titles))
    return titles


def lrclib_lyrics(http: httpx.Client, track: str, artist_name: str) -> str | None:
    """Mejor letra (plana) de LRCLIB para ese tema del artista. Evita versiones
    en directo/fragmentos; elige la letra más larga (la de estudio completa)."""
    r = http.get(f"{_LRC}/search", params={"q": f"{artist_name} {track}"})
    if r.status_code != 200:
        return None
    want = _norm(track)
    cands = []
    for x in r.json():
        if "extremoduro" not in (x.get("artistName") or "").lower():
            continue
        name = (x.get("trackName") or "")
        if _norm(name) != want:
            continue
        if re.search(r"live|directo|fragmento|en vivo", name, re.IGNORECASE):
            continue
        ly = x.get("plainLyrics")
        if ly and ly.strip():
            cands.append(ly)
    if not cands:
        return None
    return max(cands, key=len)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artist", required=True, help="slug del artista (extremoduro|robe)")
    ap.add_argument("--album-slug", required=True)
    ap.add_argument("--year", type=int, default=None,
                    help="Restringe la release de MusicBrainz a ese año.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with SessionLocal() as db, httpx.Client(timeout=30.0, headers=_UA) as http:
        artist = db.query(Artist).filter(Artist.slug == args.artist).one_or_none()
        if not artist:
            logger.error("artista %s no en BD (¿seed_catalog?)", args.artist)
            return
        album = (db.query(Album)
                 .filter(Album.artist_id == artist.id, Album.slug == args.album_slug)
                 .one_or_none())
        if not album:
            logger.error("álbum %s no en BD (¿seed_catalog?)", args.album_slug)
            return

        titles = mb_tracklist(http, album.title, artist.name, year=args.year)
        if not titles:
            logger.warning("MusicBrainz no tiene tracklist para «%s»", album.title)
            return

        ok = miss = 0
        for i, title in enumerate(titles, start=1):
            lyrics = lrclib_lyrics(http, title, artist.name)
            if not lyrics:
                logger.warning("  ✗ sin letra en LRCLIB: %s", title)
                miss += 1
                continue
            logger.info("  ✓ %s (%d chars)", title, len(lyrics))
            if args.dry_run:
                ok += 1
                continue
            track = FetchedTrack(track_number=i, genius_id=None, genius_url=None,
                                 title=title, raw_lyrics=lyrics)
            upsert_song_with_lyrics(db, album.id, track, i)
            ok += 1
        if not args.dry_run:
            db.commit()
        logger.info("Hecho: %d con letra, %d sin letra (album %s)", ok, miss, args.album_slug)


if __name__ == "__main__":
    main()
