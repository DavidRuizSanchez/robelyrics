"""Siembra grupos/sellos (data/bands.yaml) en la tabla `bands`.

Enriquece desde Wikipedia/Wikidata (Q-ID, bio corta, imagen P18 vía Commons),
reutilizando los helpers de seed_persons. Idempotente por slug.

Uso:
  python -m scripts.seed_bands
  python -m scripts.seed_bands --slug marea
  python -m scripts.seed_bands --no-enrich
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import httpx
import yaml

from app.db.models import Band
from app.db.session import SessionLocal
from app.services.instagram import photo_finder
from scripts.seed_persons import (
    _enrich_from_wikidata,
    _resolve_entities,
    _wikidata_qid_from_wikipedia,
    _wikipedia_extract,
    _wikipedia_fulltext,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BANDS_PATH = Path("/app/data/bands.yaml")
_UA = {"User-Agent": "RobeLyrics/1.0 (https://entreinteriores.com; davidruizsanchez@gmail.com)"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", help="Procesa solo un grupo.")
    ap.add_argument("--no-enrich", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load(BANDS_PATH.read_text()) or {}
    entries = cfg.get("bands", [])

    with SessionLocal() as db, httpx.Client(timeout=25.0, headers=_UA) as http:
        for entry in entries:
            slug = entry["slug"]
            if args.slug and slug != args.slug:
                continue
            band = db.query(Band).filter(Band.slug == slug).first()
            if band is None:
                band = Band(slug=slug, name=entry["name"])
                db.add(band)
            band.name = entry["name"]
            band.kind = entry.get("kind", "band")
            if entry.get("wikipedia_url"):
                band.wikipedia_url = entry["wikipedia_url"]
            if entry.get("wikidata_id"):
                band.wikidata_id = entry["wikidata_id"]
            if entry.get("related_note"):
                band.related_note = " ".join(entry["related_note"].split())
            if entry.get("founded_year"):
                band.founded_year = entry["founded_year"]
            if entry.get("members"):
                band.members = entry["members"]

            if not args.no_enrich:
                if not band.wikidata_id and band.wikipedia_url:
                    try:
                        qid = _wikidata_qid_from_wikipedia(http, band.wikipedia_url)
                        if qid:
                            band.wikidata_id = qid
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("  qid lookup falló (%s): %s", slug, exc)
                if not band.bio_short and band.wikipedia_url:
                    try:
                        band.bio_short = _wikipedia_extract(http, band.wikipedia_url)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("  wiki extract falló (%s): %s", slug, exc)
                # bio_long: artículo completo (datos concretos para no divagar).
                if band.wikipedia_url:
                    full = _wikipedia_fulltext(http, band.wikipedia_url)
                    if full:
                        band.bio_long = full
                # Miembros reales desde Wikidata P527 (has part), si el yaml no
                # los trae a mano. Resuelve los Q-ID a nombres.
                if band.wikidata_id and not band.members:
                    try:
                        enr = _enrich_from_wikidata(http, band.wikidata_id)
                        part_qids = enr.get("has_part_qids", [])[:12]
                        if part_qids:
                            people = _resolve_entities(http, part_qids)
                            members = [{"name": p["name"]} for p in people if p.get("name")]
                            if members:
                                band.members = members
                                logger.info("  members(P527): %s",
                                            ", ".join(m["name"] for m in members[:6]))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("  wikidata members falló (%s): %s", slug, exc)
                # Foto por NOMBRE solo si hay wikidata_id (entidad verificable);
                # si no, nombres comunes casan con homónimos. Mejor sin foto.
                if not band.image_url and band.wikidata_id:
                    foto = photo_finder._wikidata_photo(band.name)
                    if foto:
                        band.image_url = foto["url"]
                        band.image_attribution = foto["credit"]
                        band.image_license = "CC"
            db.commit()
            logger.info("✓ %-22s wd=%s · bio=%s · img=%s", slug,
                        band.wikidata_id or "-", bool(band.bio_short), bool(band.image_url))


if __name__ == "__main__":
    main()
