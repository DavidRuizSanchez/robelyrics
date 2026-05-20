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
import re
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import yaml
from sqlalchemy import select

from app.db.models import Artist, BandMembership, Person
from app.db.session import SessionLocal
from app.services.wikimedia import get_file_info, search_image

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


def _wikipedia_page_image(
    client: httpx.Client, wikipedia_url: str
) -> str | None:
    """Devuelve el filename Commons de la imagen principal (infobox) de la
    página Wikipedia ES, o None. Usa `prop=pageimages|pageprops` con
    `piprop=name` para sacar el filename sin redirecciones intermedias.
    """
    if "/wiki/" not in wikipedia_url:
        return None
    title = (
        wikipedia_url.rsplit("/wiki/", 1)[-1].replace("_", " ").split("#", 1)[0]
    )
    try:
        resp = client.get(
            "https://es.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "format": "json",
                "titles": title,
                "prop": "pageimages",
                "piprop": "name",
            },
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        return None
    pages = resp.json().get("query", {}).get("pages", {}) or {}
    for _, page in pages.items():
        name = page.get("pageimage")
        if name:
            return name
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
    """Trae fechas, lugar de nacimiento y referencias a bandas/obras/oficios.

    Extrae:
      - P569 (date of birth), P570 (date of death)
      - P19 (place of birth)
      - P463 (member of) → other_bands [Q-ID + name + url]
      - P800 (notable work) → notable_works
      - P106 (occupation) → occupations
    """
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
                y, m, d = time_str.lstrip("+").split("T")[0].split("-")
                return date(int(y), int(m), int(d))
            except (ValueError, IndexError):
                continue
        return None

    def _qids_from(prop: str) -> list[str]:
        out_qids: list[str] = []
        for c in claims.get(prop, []) or []:
            snak = c.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            qid_ref = snak.get("id")
            if isinstance(qid_ref, str) and qid_ref.startswith("Q"):
                out_qids.append(qid_ref)
        return out_qids

    def _string_from(prop: str) -> str | None:
        for c in claims.get(prop, []) or []:
            snak = c.get("mainsnak", {}).get("datavalue", {}).get("value")
            if isinstance(snak, str) and snak.strip():
                return snak.strip()
        return None

    out["birth_date"] = _date_from("P569")
    out["death_date"] = _date_from("P570")
    out["member_of_qids"] = _qids_from("P463")
    out["notable_work_qids"] = _qids_from("P800")
    out["occupation_qids"] = _qids_from("P106")
    # P18 (image): nombre canónico del fichero Commons. Permite usar la foto
    # "oficial" de la persona en Wikidata (la que se ve en Wikipedia infobox)
    # en vez de buscar al voleo en Commons.
    out["image_filename"] = _string_from("P18")
    return out


def _resolve_entities(
    client: httpx.Client, qids: list[str]
) -> list[dict[str, str | None]]:
    """Resuelve una lista de Q-IDs a {name, wikidata_id, wikidata_url,
    wikipedia_url}. Una sola request via wbgetentities (batch), labels y
    sitelinks en es. Filtra los que no tengan label.
    """
    if not qids:
        return []
    # Wikidata acepta hasta 50 ids por request
    out: list[dict[str, str | None]] = []
    for chunk_start in range(0, len(qids), 50):
        chunk = qids[chunk_start : chunk_start + 50]
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(chunk),
            "props": "labels|sitelinks",
            "languages": "es|en",
            "sitefilter": "eswiki",
        }
        try:
            resp = client.get("https://www.wikidata.org/w/api.php", params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError:
            continue
        for qid in chunk:
            ent = data.get("entities", {}).get(qid, {}) or {}
            labels = ent.get("labels", {}) or {}
            name = (
                (labels.get("es") or {}).get("value")
                or (labels.get("en") or {}).get("value")
            )
            if not name:
                continue
            sitelink = (ent.get("sitelinks", {}) or {}).get("eswiki") or {}
            wp_title = sitelink.get("title")
            wp_url = (
                f"https://es.wikipedia.org/wiki/{wp_title.replace(' ', '_')}"
                if wp_title
                else None
            )
            out.append({
                "name": name,
                "wikidata_id": qid,
                "wikidata_url": f"https://www.wikidata.org/wiki/{qid}",
                "wikipedia_url": wp_url,
            })
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

                # Enriquecimiento opcional. IMPORTANTE: reinicializar
                # `enriched` por iteración para no heredar valores de la
                # persona anterior si esta no tiene wikidata_id.
                enriched: dict = {}
                if not args.no_enrich:
                    if not person.wikidata_id and person.wikipedia_url:
                        try:
                            qid = _wikidata_qid_from_wikipedia(http, person.wikipedia_url)
                            if qid:
                                person.wikidata_id = qid
                                logger.info("  Q-ID: %s", qid)
                        except httpx.HTTPError as e:
                            logger.warning("  wikidata lookup failed: %s", e)

                    if person.wikidata_id:
                        try:
                            enriched = _enrich_from_wikidata(http, person.wikidata_id)
                            if not person.birth_date and enriched.get("birth_date"):
                                person.birth_date = enriched["birth_date"]
                            if not person.death_date and enriched.get("death_date"):
                                person.death_date = enriched["death_date"]

                            # Bandas externas (Wikidata P463) — excluyendo
                            # las que ya tenemos como memberships en nuestro
                            # Artist corpus. Como Wikidata tiene varios Q-IDs
                            # apuntando al mismo grupo (Extremoduro aparece
                            # como Q263632, Q1238849, Q2311472 según el
                            # claim/persona), filtramos también por nombre
                            # normalizado contra los slugs del corpus.
                            internal_qids = {"Q263632", "Q1238849", "Q2311472", "Q3500822"}
                            internal_names = {"extremoduro", "robe"}
                            member_qids = [
                                q for q in enriched.get("member_of_qids", [])
                                if q not in internal_qids
                            ]
                            if member_qids:
                                bands = _resolve_entities(http, member_qids)
                                # filtra por nombre normalizado
                                bands = [
                                    b for b in bands
                                    if b["name"].strip().lower() not in internal_names
                                ]
                                person.other_bands = bands
                                logger.info(
                                    "  other_bands: %d (%s)",
                                    len(bands),
                                    ", ".join(b["name"] for b in bands[:5]),
                                )

                            works_qids = enriched.get("notable_work_qids", [])
                            if works_qids:
                                works = _resolve_entities(http, works_qids)
                                person.notable_works = works
                                logger.info(
                                    "  notable_works: %d",
                                    len(works),
                                )

                            occ_qids = enriched.get("occupation_qids", [])
                            if occ_qids:
                                occs = _resolve_entities(http, occ_qids)
                                person.occupations = occs
                        except httpx.HTTPError as e:
                            logger.warning("  wikidata enrich failed: %s", e)

                    if not person.bio_short and person.wikipedia_url:
                        try:
                            extract = _wikipedia_extract(http, person.wikipedia_url)
                            if extract:
                                person.bio_short = extract[:500]
                        except httpx.HTTPError as e:
                            logger.warning("  wikipedia extract failed: %s", e)

                    # Foto: 0) image_filename hardcoded en yaml (override).
                    # 1) P18 de Wikidata (foto oficial Wikidata).
                    # 2) Imagen principal del artículo Wikipedia (infobox).
                    # 3) Fallback search Commons con filtro estricto.
                    if not person.image_url and entry.get("image_filename"):
                        img = get_file_info(entry["image_filename"])
                        if img:
                            person.image_url = img.thumb_url
                            person.image_attribution = img.attribution_text
                            person.image_license = img.license_short
                            person.image_source_url = img.source_page_url
                            logger.info(
                                "  Imagen (yaml hardcoded): %s",
                                img.source_page_url,
                            )
                    if not person.image_url and enriched.get("image_filename"):
                        img = get_file_info(enriched["image_filename"])
                        if img:
                            person.image_url = img.thumb_url
                            person.image_attribution = img.attribution_text
                            person.image_license = img.license_short
                            person.image_source_url = img.source_page_url
                            logger.info(
                                "  Imagen (Wikidata P18): %s",
                                img.source_page_url,
                            )

                    if not person.image_url and person.wikipedia_url:
                        try:
                            wp_filename = _wikipedia_page_image(http, person.wikipedia_url)
                        except Exception:
                            wp_filename = None
                        if wp_filename:
                            img = get_file_info(wp_filename)
                            if img:
                                person.image_url = img.thumb_url
                                person.image_attribution = img.attribution_text
                                person.image_license = img.license_short
                                person.image_source_url = img.source_page_url
                                logger.info(
                                    "  Imagen (Wikipedia pageimage): %s",
                                    img.source_page_url,
                                )
                    if not person.image_url:
                        # Fallback: búsqueda Commons con filtro ESTRICTO de
                        # nombre. Requiere que el filename contenga al menos
                        # 2 tokens distintos del nombre completo (apellido +
                        # nombre o nombre + stage). Si solo un token coincide
                        # ("robe" en "Robe Lighthouse"), rechaza — mejor sin
                        # foto que con foto que no es de la persona.
                        queries: list[str] = []
                        if person.full_name:
                            queries.append(person.full_name)
                        if person.stage_name and person.stage_name != person.full_name:
                            queries.append(person.stage_name)
                        all_tokens = set(
                            t.lower()
                            for t in re.findall(
                                r"[A-Za-zÁÉÍÓÚáéíóúÑñ]{4,}",
                                (person.full_name or "") + " " + (person.stage_name or ""),
                            )
                        )
                        require_n = 2 if len(all_tokens) >= 2 else 1
                        for q in queries:
                            cand = search_image(q)
                            if cand is None:
                                continue
                            fn_lower = cand.title.lower()
                            matched = sum(1 for tok in all_tokens if tok in fn_lower)
                            if matched >= require_n:
                                person.image_url = cand.thumb_url
                                person.image_attribution = cand.attribution_text
                                person.image_license = cand.license_short
                                person.image_source_url = cand.source_page_url
                                logger.info(
                                    "  Imagen (Commons search %r, %d tokens): %s",
                                    q, matched, cand.source_page_url,
                                )
                                break
                            else:
                                logger.info(
                                    "  Rechazada (%d/%d tokens en %r)",
                                    matched, require_n, fn_lower,
                                )

                # Memberships
                _reconcile_memberships(db, person, entry.get("memberships") or [])
                db.commit()

            logger.info("Total procesado: %d persona(s)", len(entries))


if __name__ == "__main__":
    main()
