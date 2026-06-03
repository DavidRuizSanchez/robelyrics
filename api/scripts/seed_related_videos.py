"""Siembra vídeos relacionados (data/related_videos.yaml) en las tablas
`related_videos` y `related_video_entities`.

Idempotente por youtube_id: upserta cada vídeo y reconcilia sus anclas de
entidad (añade las nuevas del YAML y borra las que ya no figuran, para que el
YAML sea la fuente de verdad). Espejo del estilo de seed_bands / seed_taxonomies.

Uso:
    docker compose exec api python -m scripts.seed_related_videos
    docker compose exec api python -m scripts.seed_related_videos --youtube-id wFUU00eY1Rc
"""
from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

import yaml

from app.db.models import RelatedVideo, RelatedVideoEntity
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

YAML_PATH = Path("/app/data/related_videos.yaml")

# Mapeo de las listas del bloque `links` al entity_type de la tabla join.
_LINK_KEYS = {
    "persons": "person",
    "artists": "artist",
    "bands": "band",
    "songs": "song",
}


def _parse_date(value) -> date | None:
    """Acepta date (lo da PyYAML) o string YYYY-MM-DD."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        logger.warning("  fecha no parseable: %r", value)
        return None


def _desired_links(entry: dict) -> set[tuple[str, str]]:
    """Conjunto (entity_type, entity_slug) declarado para un vídeo en el YAML."""
    out: set[tuple[str, str]] = set()
    links = entry.get("links") or {}
    for yaml_key, entity_type in _LINK_KEYS.items():
        for slug in links.get(yaml_key) or []:
            slug = (slug or "").strip()
            if slug:
                out.add((entity_type, slug))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--youtube-id", help="Procesa solo un vídeo.")
    args = ap.parse_args()

    cfg = yaml.safe_load(YAML_PATH.read_text()) or {}
    entries = cfg.get("videos", [])

    with SessionLocal() as db:
        for entry in entries:
            yid = entry["youtube_id"]
            if args.youtube_id and yid != args.youtube_id:
                continue

            video = (
                db.query(RelatedVideo)
                .filter(RelatedVideo.youtube_id == yid)
                .first()
            )
            if video is None:
                video = RelatedVideo(youtube_id=yid)
                db.add(video)
            video.title = entry["title"]
            video.kind = entry.get("kind", "official")
            video.upload_date = _parse_date(entry.get("upload_date"))
            db.flush()

            # Reconcilia anclas: el YAML es la fuente de verdad.
            desired = _desired_links(entry)
            existing = {
                (e.entity_type, e.entity_slug): e for e in video.entities
            }
            for key in existing.keys() - desired:
                db.delete(existing[key])
            for entity_type, entity_slug in desired - existing.keys():
                db.add(
                    RelatedVideoEntity(
                        video_id=video.id,
                        entity_type=entity_type,
                        entity_slug=entity_slug,
                    )
                )

            db.commit()
            logger.info(
                "✓ %-13s %-13s · %d anclas",
                yid,
                video.kind,
                len(desired),
            )


if __name__ == "__main__":
    main()
