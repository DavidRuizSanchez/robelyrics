"""Backfill de `albums.release_date` desde Wikipedia + Wikidata entity API.

Idempotente. Para cada álbum sin `release_date`:
  1. Busca la página de Wikipedia ES por título (forma `"{title} (álbum)"`).
  2. Extrae el `wikibase_item` (Q-ID) del page via pageprops.
  3. Fetcha la entidad Wikidata directa (`Special:EntityData/{qid}.json`) y
     extrae P577 (publication date).
  4. Update `release_date` + `release_date_source = 'wikidata:{qid}'`.

Evita SPARQL porque tiene rate-limiting agresivo durante outages. La API de
páginas y de entidades es muchísimo más permisiva.

Uso:
    python -m scripts.seed_album_dates                # rellena los NULL
    python -m scripts.seed_album_dates --force        # sobrescribe todos
    python -m scripts.seed_album_dates --artist robe
    python -m scripts.seed_album_dates --dry-run
"""
from __future__ import annotations

import argparse
import logging
import re
import unicodedata
from datetime import date

import httpx
from sqlalchemy import select

from app.db.models import Album, Artist
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

USER_AGENT = (
    "RobeLyrics/1.0 (https://entreinteriores.com; davidruizsanchez@gmail.com) httpx"
)
WIKIPEDIA_API = "https://es.wikipedia.org/w/api.php"
WIKIDATA_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _search_wikipedia_page(
    client: httpx.Client, album_title: str, artist_name: str
) -> str | None:
    """Devuelve el title canónico de la página ES más relevante, o None."""
    queries = [
        f"{album_title} (álbum) {artist_name}",
        f"{album_title} álbum de {artist_name}",
        f"{album_title} {artist_name}",
    ]
    norm_album = _normalize(album_title)
    for query in queries:
        resp = client.get(
            WIKIPEDIA_API,
            params={
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": query,
                "srlimit": "5",
                "srnamespace": "0",
            },
        )
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", []) or []
        for r in results:
            title = r.get("title", "")
            if not title:
                continue
            norm_title = _normalize(title)
            # Match si el título contiene normalizado el álbum
            if norm_album in norm_title:
                return title
        if results:
            # Heurística suelta: el primer resultado
            return results[0]["title"]
    return None


def _qid_for_page(client: httpx.Client, title: str) -> str | None:
    resp = client.get(
        WIKIPEDIA_API,
        params={
            "action": "query",
            "format": "json",
            "titles": title,
            "prop": "pageprops",
            "ppprop": "wikibase_item",
        },
    )
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {}) or {}
    for _, page in pages.items():
        qid = (page.get("pageprops") or {}).get("wikibase_item")
        if qid:
            return qid
    return None


def _release_date_for_qid(client: httpx.Client, qid: str) -> date | None:
    resp = client.get(WIKIDATA_ENTITY.format(qid=qid))
    resp.raise_for_status()
    entity = resp.json().get("entities", {}).get(qid, {})
    claims = entity.get("claims", {}).get("P577", []) or []
    if not claims:
        return None
    # P577 con preferencia "preferred" o el primero
    sorted_claims = sorted(
        claims, key=lambda c: c.get("rank") == "preferred", reverse=True
    )
    for claim in sorted_claims:
        snak = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        time_str = snak.get("time", "")  # "+1996-04-15T00:00:00Z"
        precision = snak.get("precision", 11)  # 11 = day, 10 = month, 9 = year
        # Solo aceptamos precisión de día: si solo conocemos año o mes, mejor
        # NULL y que el admin lo rellene a mano. Si no, los aniversarios
        # caerían el 1 de enero o el 1 del mes, que no es el aniversario real.
        if precision < 11:
            continue
        m = re.match(r"^\+?(\d{4})-(\d{2})-(\d{2})T", time_str)
        if not m:
            continue
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--artist", help="Slug de artist concreto")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    with httpx.Client(timeout=20.0, headers=headers, follow_redirects=True) as client:
        with SessionLocal() as db:
            q = select(Album, Artist).join(Artist, Album.artist_id == Artist.id)
            if args.artist:
                q = q.where(Artist.slug == args.artist)
            rows = db.execute(q).all()

            updated = 0
            skipped = 0
            not_found = 0
            for album, artist in rows:
                if album.release_date is not None and not args.force:
                    skipped += 1
                    continue

                logger.info("Buscando %r de %s...", album.title, artist.name)
                page_title = _search_wikipedia_page(client, album.title, artist.name)
                if not page_title:
                    logger.warning("  Sin página Wikipedia")
                    not_found += 1
                    continue

                qid = _qid_for_page(client, page_title)
                if not qid:
                    logger.warning("  Sin Q-ID en %r", page_title)
                    not_found += 1
                    continue

                release = _release_date_for_qid(client, qid)
                if release is None:
                    logger.warning("  Sin P577 en %s (página %r)", qid, page_title)
                    not_found += 1
                    continue

                # Sanity: el año debe coincidir o ser próximo al year local
                if abs(release.year - album.year) > 1:
                    logger.warning(
                        "  Año Wikidata (%d) muy distinto de local (%d) para %r — skip",
                        release.year, album.year, album.title,
                    )
                    not_found += 1
                    continue

                logger.info(
                    "  → %s (Wikidata %s, página %r)",
                    release.isoformat(), qid, page_title,
                )
                if not args.dry_run:
                    album.release_date = release
                    album.release_date_source = f"wikidata:{qid}"
                updated += 1

            if not args.dry_run:
                db.commit()
            logger.info(
                "Total: actualizados=%d, ya tenían=%d, sin match=%d",
                updated, skipped, not_found,
            )


if __name__ == "__main__":
    main()
