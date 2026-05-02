"""Descarga las portadas oficiales de cada disco vía MusicBrainz + Cover Art Archive.

Estrategia (gratis, sin auth):
  1. Para cada album sin `cover_url`:
     - GET https://musicbrainz.org/ws/2/release-group/?query=...&fmt=json
     - Coge el primer release-group que matchee artist + title.
     - GET https://coverartarchive.org/release-group/{mbid}/front-500
     - Guarda como web/public/album-covers/{slug}.jpg
     - UPDATE albums SET cover_url = '/album-covers/{slug}.jpg'

Idempotente. Rate limit 1 req/s a MusicBrainz (recomendación oficial).

Ejecución: docker compose exec api python -m scripts.match_covers
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import update

from app.db.models import Album, Artist
from scripts.research.common import get_session, log

MB_API = "https://musicbrainz.org/ws/2"
CAA_API = "https://coverartarchive.org"
USER_AGENT = "RobeLyrics/0.1 (personal use; davidruizsanchez@gmail.com)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

# /app/data está montado en compose; las portadas van a /app/web-public via mount adicional
# o copiamos a un dir compartido. Por simplicidad: bind-mount web/public en api.
COVERS_DIR = Path("/app/web-public/album-covers")


def _mb_query(client: httpx.Client, query: str) -> list[dict]:
    try:
        r = client.get(
            f"{MB_API}/release-group",
            params={"query": query, "fmt": "json", "limit": 5},
            headers=HEADERS,
        )
    except httpx.HTTPError as e:
        log(f"  MB error: {e}", "warn")
        return []
    if r.status_code != 200:
        return []
    items = r.json().get("release-groups", [])
    items.sort(key=lambda x: x.get("score", 0), reverse=True)
    return items


def search_release_group(
    client: httpx.Client, artist: str, title: str
) -> str | None:
    """Devuelve el mbid del primer release-group que matchee.
    Estrategias en orden: artist+title exacto, alias del artista, solo title."""
    queries = [f'artist:"{artist}" AND releasegroup:"{title}"']
    # Aliases comunes del artista
    if "Robe" in artist:
        queries.append(f'artist:"Robe" AND releasegroup:"{title}"')
        queries.append(f'artist:"Roberto Iniesta" AND releasegroup:"{title}"')
    # Fallback: solo título (riesgo de match falso, pero el catálogo es pequeño)
    queries.append(f'releasegroup:"{title}"')

    for q in queries:
        items = _mb_query(client, q)
        if items:
            return items[0].get("id")
    return None


def download_cover(
    client: httpx.Client, mbid: str, dest: Path
) -> bool:
    url = f"{CAA_API}/release-group/{mbid}/front-500"
    try:
        with client.stream("GET", url, follow_redirects=True, headers=HEADERS) as r:
            if r.status_code != 200:
                log(f"  CAA HTTP {r.status_code} para mbid={mbid}", "warn")
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        return True
    except httpx.HTTPError as e:
        log(f"  CAA error: {e}", "warn")
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Reescribir aunque ya tenga cover")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    n_done = 0
    n_skipped = 0
    n_failed = 0

    # Materializar a tuplas para no depender de sesión durante el HTTP
    with get_session() as db:
        rows = (
            db.query(Album, Artist)
            .join(Artist, Album.artist_id == Artist.id)
            .all()
        )
        items = [
            (a.id, a.slug, a.title, a.cover_url, ar.name)
            for a, ar in rows
        ]
    log(f"álbumes en BD: {len(items)}")

    with httpx.Client(timeout=15) as client:
        for album_id, slug, title, cover_url, artist_name in items:
            if cover_url and not args.force:
                n_skipped += 1
                continue
            if args.limit and n_done >= args.limit:
                break

            log(f"album · {title} · {artist_name}")
            time.sleep(1.0)  # Rate limit MB
            mbid = search_release_group(client, artist_name, title)
            if not mbid:
                log(f"  ✗ no encontrado en MusicBrainz", "warn")
                n_failed += 1
                continue
            log(f"  mbid={mbid}")
            time.sleep(0.5)
            dest = COVERS_DIR / f"{slug}.jpg"
            ok = download_cover(client, mbid, dest)
            if not ok:
                n_failed += 1
                continue

            # UPDATE en su propia sesión
            with get_session() as db:
                db.execute(
                    update(Album)
                    .where(Album.id == album_id)
                    .values(cover_url=f"/album-covers/{slug}.jpg")
                )
            n_done += 1
            log(f"  ✓ → /album-covers/{slug}.jpg")

    log(f"descargadas: {n_done} · sin match: {n_failed} · skip: {n_skipped}", "ok")


if __name__ == "__main__":
    main()
