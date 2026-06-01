"""Prefetch de imágenes adicionales por disco desde Cover Art Archive.

Para cada álbum de la discografía busca su release en MusicBrainz y recoge las
imágenes oficiales disponibles en Cover Art Archive (portada, contraportada,
libreto, disco…). Guarda el resultado en `data/album_media.json`:

    { "<slug>": [ {"type": "Back", "url": "https://…"}, … ], … }

Usar esas imágenes (arte oficial del propio disco) para hablar de ese disco es
uso editorial normalizado y de riesgo mínimo, igual que la portada.

Idempotente: re-ejecutar reescribe el JSON. Respeta el límite de MusicBrainz
(1 req/s). Uso:  python -m scripts.instagram.fetch_album_media
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx
from sqlalchemy import select

from app.db.models import Album, Artist
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# `/app/data` va montado read-only en prod; este prefetch escribe a /tmp y el
# operador copia el resultado a `data/album_media.json` (lo lee album_cover).
OUT_PATH = Path("/tmp/album_media.json")
UA = {"User-Agent": "EntreInteriores/1.0 (https://entreinteriores.com; davidruizsanchez@gmail.com)"}
MB = "https://musicbrainz.org/ws/2"
CAA = "https://coverartarchive.org"
MAX_RELEASES_CHECK = 8  # cuántos releases inspeccionar por disco


def _mb(path: str, **params) -> dict:
    params["fmt"] = "json"
    r = httpx.get(f"{MB}/{path}", params=params, headers=UA, timeout=25.0)
    r.raise_for_status()
    return r.json()


def _caa_release(rid: str) -> list[dict] | None:
    try:
        r = httpx.get(f"{CAA}/release/{rid}", headers=UA, timeout=25.0,
                      follow_redirects=True)
        if r.status_code != 200:
            return None
        return r.json().get("images", [])
    except Exception:  # noqa: BLE001
        return None


def _best_url(img: dict) -> str | None:
    th = img.get("thumbnails", {}) or {}
    return th.get("1200") or th.get("large") or th.get("500") or img.get("image")


def _media_for_album(title: str, artist: str) -> list[dict]:
    """Devuelve la lista de imágenes (type+url) del mejor release con arte."""
    rg = _mb("release-group",
             query=f'artist:"{artist}" AND releasegroup:"{title}"', limit=2)
    groups = rg.get("release-groups", [])
    if not groups:
        time.sleep(1.1)
        rg = _mb("release-group", query=f'releasegroup:"{title}"', limit=2)
        groups = rg.get("release-groups", [])
    if not groups:
        return []
    rgid = groups[0]["id"]
    time.sleep(1.1)
    releases = _mb("release", **{"release-group": rgid, "limit": 25}).get("releases", [])

    best: list[dict] = []
    for rel in releases[:MAX_RELEASES_CHECK]:
        imgs = _caa_release(rel["id"]) or []
        if len(imgs) > len(best):
            best = imgs
        if len(best) >= 4:  # suficiente variedad, no seguir gastando llamadas
            break
    out = []
    seen_types = set()
    for img in best:
        url = _best_url(img)
        if not url:
            continue
        types = img.get("types") or (["Front"] if img.get("front") else ["Other"])
        key = "/".join(types)
        # Una imagen por tipo (evita 2 "Front" iguales).
        if key in seen_types:
            continue
        seen_types.add(key)
        out.append({"type": key, "url": url})
    return out


def main() -> None:
    result: dict[str, list[dict]] = {}
    with SessionLocal() as db:
        rows = db.execute(
            select(Album.slug, Album.title, Artist.name)
            .join(Artist, Artist.id == Album.artist_id)
            .order_by(Album.year)
        ).all()
    for slug, title, artist in rows:
        try:
            media = _media_for_album(title, artist)
        except Exception as exc:  # noqa: BLE001
            logger.warning("  %s: error (%s)", slug, exc)
            media = []
        result[slug] = media
        logger.info("%-40s %d imágenes: %s", title, len(media),
                    [m["type"] for m in media])
        time.sleep(1.1)

    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    total = sum(len(v) for v in result.values())
    logger.info("Escrito %s · %d discos · %d imágenes", OUT_PATH,
                len(result), total)


if __name__ == "__main__":
    main()
