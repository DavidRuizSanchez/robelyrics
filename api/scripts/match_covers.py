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

    TODAS las consultas llevan artista. Aquí había un tercer intento con
    `releasegroup:"{title}"` **sin filtrar por artista**, justificado en que «el
    catálogo es pequeño». Es el mismo patrón de buscar-por-nombre-y-asignar que
    coló tocino ucraniano como «Salo» y a Fito Páez como Fito Cabrales; en
    portadas ya produjo su propio caso (la de «Rock transgresivo» servida como la
    de «Tú en tu casa…», ver data/reference/). Sin artista no se asigna: se deja
    sin portada y se reporta.
    """
    queries = [f'artist:"{artist}" AND releasegroup:"{title}"']
    # Aliases del artista: en MusicBrainz el solista figura como «Robe», no como
    # «Robe Iniesta», que es lo que guarda nuestra BD.
    if "Robe" in artist:
        queries.append(f'artist:"Robe" AND releasegroup:"{title}"')
        queries.append(f'artist:"Roberto Iniesta" AND releasegroup:"{title}"')

    for i, q in enumerate(queries):
        # MusicBrainz limita a 1 req/s y responde 503 si te pasas; `_mb_query`
        # convierte ese 503 en lista vacía, así que sin esta pausa las consultas
        # de alias se descartaban en silencio y parecía que el disco no existía.
        # Es lo que dejaba sin portada a «Bienvenidos al temporal», y lo que
        # hacía parecer necesario el fallback sin artista.
        if i:
            time.sleep(1.1)
        items = _mb_query(client, q)
        if items:
            return items[0].get("id")
    return None


def fetch_license(client: httpx.Client, mbid: str) -> str | None:
    """Licencia que declara el uploader en CAA para la imagen frontal.

    Es el dato que `docs/legal-audit.md` §3.5 pide registrar. Si CAA no la
    declara se devuelve None y la columna queda NULL — no se supone nada.
    """
    try:
        r = client.get(f"{CAA_API}/release-group/{mbid}", follow_redirects=True,
                       headers=HEADERS, timeout=30)
        if r.status_code != 200:
            return None
        for im in r.json().get("images", []):
            if im.get("front"):
                # CAA expone la licencia en `license` (URL de CC) cuando existe.
                lic = im.get("license")
                if lic:
                    return str(lic)[:64]
                return "sin declarar"
    except (httpx.HTTPError, ValueError):
        return None
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
    parser.add_argument("--album-slug", action="append",
                        help="limitar a estos slugs (repetible)")
    parser.add_argument("--only-provenance", action="store_true",
                        help="no descarga: solo rellena mbid/licencia de las que ya tienen portada")
    args = parser.parse_args()

    n_done = 0
    n_skipped = 0
    n_failed = 0
    n_prov = 0

    # Materializar a tuplas para no depender de sesión durante el HTTP
    with get_session() as db:
        q = db.query(Album, Artist).join(Artist, Album.artist_id == Artist.id)
        if args.album_slug:
            q = q.filter(Album.slug.in_(args.album_slug))
        rows = q.all()
        items = [
            (a.id, a.slug, a.title, a.cover_url, ar.name, a.cover_mbid)
            for a, ar in rows
        ]
    log(f"álbumes en BD: {len(items)}")

    with httpx.Client(timeout=15) as client:
        for album_id, slug, title, cover_url, artist_name, cover_mbid in items:
            tiene_portada = bool(cover_url)

            # Modo procedencia: la portada ya está, solo falta saber de dónde
            # salió y con qué licencia (docs/legal-audit.md §3.5).
            if args.only_provenance:
                if not tiene_portada or (cover_mbid and not args.force):
                    n_skipped += 1
                    continue
                log(f"procedencia · {title}")
                time.sleep(1.0)
                mbid = search_release_group(client, artist_name, title)
                if not mbid:
                    log("  ✗ no encontrado en MusicBrainz", "warn")
                    n_failed += 1
                    continue
                time.sleep(0.5)
                lic = fetch_license(client, mbid)
                with get_session() as db:
                    db.execute(
                        update(Album).where(Album.id == album_id)
                        .values(cover_mbid=mbid, cover_license=lic, cover_source="caa")
                    )
                n_prov += 1
                log(f"  ✓ mbid={mbid} · licencia={lic or '—'}")
                continue

            if tiene_portada and not args.force:
                n_skipped += 1
                continue
            if args.limit and n_done >= args.limit:
                break

            log(f"album · {title} · {artist_name}")
            time.sleep(1.0)  # Rate limit MB
            mbid = search_release_group(client, artist_name, title)
            if not mbid:
                log("  ✗ no encontrado en MusicBrainz", "warn")
                n_failed += 1
                continue
            log(f"  mbid={mbid}")
            time.sleep(0.5)
            dest = COVERS_DIR / f"{slug}.jpg"
            ok = download_cover(client, mbid, dest)
            if not ok:
                n_failed += 1
                continue
            time.sleep(0.5)
            lic = fetch_license(client, mbid)

            # UPDATE en su propia sesión
            with get_session() as db:
                db.execute(
                    update(Album)
                    .where(Album.id == album_id)
                    .values(
                        cover_url=f"/album-covers/{slug}.jpg",
                        cover_mbid=mbid,
                        cover_license=lic,
                        cover_source="caa",
                    )
                )
            n_done += 1
            log(f"  ✓ → /album-covers/{slug}.jpg · licencia={lic or '—'}")

    log(f"descargadas: {n_done} · procedencia: {n_prov} · "
        f"sin match: {n_failed} · skip: {n_skipped}", "ok")


if __name__ == "__main__":
    main()
