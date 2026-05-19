"""Pobla `persons` + `band_memberships` desde `data/persons.yaml`.

Idempotente. Por cada persona:
  - Upsert por `slug`
  - Si falta `wikidata_id`, lo busca a partir de `wikipedia_url`
  - Si falta `bio_short`, intenta extracto de Wikipedia
  - Si falta `image_url`, busca foto libre en Wikimedia Commons
  - Reconcilia memberships: borra las que no estén en el yaml, añade las nuevas

Uso:
    python -m scripts.seed_persons
    python -m scripts.seed_persons --slug robe-iniesta
    python -m scripts.seed_persons --no-enrich   # no llama Wikipedia/Wikimedia
"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import yaml
from sqlalchemy import select

from app.db.models import Artist, BandMembership, Person
from app.db.session import SessionLocal
from app.services.wikimedia import search_image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

YAML_PATH = Path("/app/data/persons.yaml")
USER_AGENT = "RobeLyrics/1.0 (https://entreinteriores.com; davidruizsanchez@gmail.com) httpx"


# --------------------------------------------------------------------------- #
# Wikipedia / Wikidata enrichment
# --------------------------------------------------------------------------- #
def _wikidata_qid_from_wikipedia(client: httpx.Client, wikipedia_url: str) -> str | None:
    """Extrae Q-ID consultando la pageprops de la página ES."""
    # Extrae title de la URL: https://es.wikipedia.org/wiki/<Title>
    if "/wiki/" not in wikipedia_url:
        return None
    title = wikipedia_url.rsplit("/wiki/", 1)[-1]
    title = httpx.URL("http://x/?t=" + title).params.get("t") or title
    # quita anchor # si lo hay
    title = title.split("#", 1)[0]

    resp = client.get(
        "https://es.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "titles": title.replace("_", " "),
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


def _wikipedia_extract(client: httpx.Client, wikipedia_url: str) -> str | None:
    """Devuelve el primer párrafo de la página ES (1-2 frases)."""
    if "/wiki/" not in wikipedia_url:
        return None
    title = wikipedia_url.rsplit("/wiki/", 1)[-1].replace("_", " ").split("#", 1)[0]
    resp = client.get(
        "https://es.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "titles": title,
            "prop": "extracts",
            "exintro": "1",
            "explaintext": "1",
            "exchars": "500",
        },
    )
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {}) or {}
    for _, page in pages.items():
        extract = page.get("extract") or ""
        if extract:
            return extract.strip()
    return None


def _enrich_from_wikidata(client: httpx.Client, qid: str) -> dict[str, Any]:
    """Trae birth_date / death_date / birth_place si están en la entity."""
    url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    resp = client.get(url)
    resp.raise_for_status()
    entity = resp.json().get("entities", {}).get(qid, {})
    claims = entity.get("claims", {})

    out: dict[str, Any] = {}

    def _date_from(prop: str) -> date | None:
        for c in claims.get(prop, []) or []:
            snak = c.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            time_str = snak.get("time", "")
            precision = snak.get("precision", 11)
            if precision < 11:
                continue
            try:
                # "+1962-05-16T00:00:00Z"
                y, m, d = time_str.lstrip("+").split("T")[0].split("-")
                return date(int(y), int(m), int(d))
            except (ValueError, IndexError):
                continue
        return None

    out["birth_date"] = _date_from("P569")
    out["death_date"] = _date_from("P570")
    return out


# --------------------------------------------------------------------------- #
# Reconciliación
# --------------------------------------------------------------------------- #
def _reconcile_memberships(db, person: Person, declared: list[dict]) -> None:
    """Crea/borra memberships para que coincidan con el yaml."""
    # Mapa de artist_slug → Artist
    artist_slugs = {m.get("artist") for m in declared if m.get("artist")}
    artists = {
        a.slug: a for a in db.execute(
            select(Artist).where(Artist.slug.in_(artist_slugs))
        ).scalars().all()
    }
    unknown = artist_slugs - set(artists.keys())
    if unknown:
        logger.warning(
            "  Artists no encontrados (skipping memberships): %s", sorted(unknown)
        )

    declared_keys: set[tuple] = set()
    for m in declared:
        artist_slug = m.get("artist")
        if artist_slug not in artists:
            continue
        artist = artists[artist_slug]
        role = m.get("role", "miembro")
        era = m.get("era")
        key = (artist.id, role, era)
        declared_keys.add(key)

        existing = next(
            (bm for bm in person.memberships
             if bm.artist_id == artist.id and bm.role == role and bm.era == era),
            None,
        )
        if existing:
            existing.is_founder = bool(m.get("is_founder", False))
            existing.is_current = bool(m.get("is_current", False))
            existing.position = int(m.get("position", 0))
            existing.notes = m.get("notes")
        else:
            bm = BandMembership(
                person_id=person.id,
                artist_id=artist.id,
                role=role,
                era=era,
                is_founder=bool(m.get("is_founder", False)),
                is_current=bool(m.get("is_current", False)),
                position=int(m.get("position", 0)),
                notes=m.get("notes"),
            )
            db.add(bm)

    # Borra memberships que ya no aparecen en el yaml
    for bm in list(person.memberships):
        if (bm.artist_id, bm.role, bm.era) not in declared_keys:
            db.delete(bm)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", help="Procesa solo una persona")
    parser.add_argument(
        "--no-enrich",
        action="store_true",
        help="No llama a Wikipedia/Wikidata/Wikimedia (solo lo del yaml).",
    )
    args = parser.parse_args()

    if not YAML_PATH.exists():
        logger.error("YAML no encontrado: %s", YAML_PATH)
        return

    with YAML_PATH.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    entries = cfg.get("persons") or []
    if args.slug:
        entries = [e for e in entries if e.get("slug") == args.slug]

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    with httpx.Client(timeout=20.0, headers=headers, follow_redirects=True) as http:
        with SessionLocal() as db:
            for entry in entries:
                slug = entry["slug"]
                logger.info("Procesando %s...", slug)

                person = db.execute(
                    select(Person).where(Person.slug == slug)
                ).scalar_one_or_none()
                if person is None:
                    person = Person(slug=slug, full_name=entry["full_name"])
                    db.add(person)
                    db.flush()

                # Campos directos del yaml
                person.full_name = entry["full_name"]
                person.stage_name = entry.get("stage_name")
                if entry.get("birth_date"):
                    person.birth_date = entry["birth_date"]
                if entry.get("death_date"):
                    person.death_date = entry["death_date"]
                person.birth_place = entry.get("birth_place")
                if entry.get("bio_short"):
                    person.bio_short = entry["bio_short"]
                person.wikipedia_url = entry.get("wikipedia_url")
                if entry.get("wikidata_id"):
                    person.wikidata_id = entry["wikidata_id"]

                # Enriquecimiento opcional
                if not args.no_enrich:
                    if not person.wikidata_id and person.wikipedia_url:
                        try:
                            qid = _wikidata_qid_from_wikipedia(http, person.wikipedia_url)
                            if qid:
                                person.wikidata_id = qid
                                logger.info("  Q-ID: %s", qid)
                        except httpx.HTTPError as e:
                            logger.warning("  wikidata lookup failed: %s", e)

                    if person.wikidata_id and (not person.birth_date or not person.death_date):
                        try:
                            enriched = _enrich_from_wikidata(http, person.wikidata_id)
                            if not person.birth_date and enriched.get("birth_date"):
                                person.birth_date = enriched["birth_date"]
                            if not person.death_date and enriched.get("death_date"):
                                person.death_date = enriched["death_date"]
                        except httpx.HTTPError as e:
                            logger.warning("  wikidata enrich failed: %s", e)

                    if not person.bio_short and person.wikipedia_url:
                        try:
                            extract = _wikipedia_extract(http, person.wikipedia_url)
                            if extract:
                                person.bio_short = extract[:500]
                        except httpx.HTTPError as e:
                            logger.warning("  wikipedia extract failed: %s", e)

                    if not person.image_url:
                        query = person.stage_name or person.full_name
                        img = search_image(query)
                        if img:
                            person.image_url = img.thumb_url
                            person.image_attribution = img.attribution_text
                            person.image_license = img.license_short
                            person.image_source_url = img.source_page_url
                            logger.info("  Imagen: %s", img.source_page_url)

                # Memberships
                _reconcile_memberships(db, person, entry.get("memberships") or [])
                db.commit()

            logger.info("Total procesado: %d persona(s)", len(entries))


if __name__ == "__main__":
    main()
