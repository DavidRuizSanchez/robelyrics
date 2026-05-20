"""Carga taxonomías (themes/places/concepts) desde data/taxonomies.yaml.

Idempotente: cada entrada se upserta por slug; los matches song↔taxonomía
sólo se añaden si no existían ya (no se borran asociaciones manuales). Pensado
para correr múltiples veces tras añadir entradas nuevas al YAML.

Uso:
    docker compose exec api python -m scripts.seed_taxonomies
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Concept,
    Place,
    Song,
    SongConcept,
    SongPlace,
    SongTheme,
    Theme,
)
from app.db.session import SessionLocal

YAML_PATH = Path("/app/data/taxonomies.yaml")


def upsert_theme(db: Session, entry: dict) -> Theme:
    row = db.execute(select(Theme).where(Theme.slug == entry["slug"])).scalar_one_or_none()
    if row:
        row.name = entry["name"]
        row.description = entry.get("description")
    else:
        row = Theme(
            slug=entry["slug"],
            name=entry["name"],
            description=entry.get("description"),
        )
        db.add(row)
    db.flush()
    return row


def upsert_place(db: Session, entry: dict) -> Place:
    row = db.execute(select(Place).where(Place.slug == entry["slug"])).scalar_one_or_none()
    if row:
        row.name = entry["name"]
        row.kind = entry.get("kind")
        row.description = entry.get("description")
        row.geo_lat = entry.get("geo_lat")
        row.geo_lng = entry.get("geo_lng")
    else:
        row = Place(
            slug=entry["slug"],
            name=entry["name"],
            kind=entry.get("kind"),
            description=entry.get("description"),
            geo_lat=entry.get("geo_lat"),
            geo_lng=entry.get("geo_lng"),
        )
        db.add(row)
    db.flush()
    return row


def upsert_concept(db: Session, entry: dict) -> Concept:
    row = db.execute(select(Concept).where(Concept.slug == entry["slug"])).scalar_one_or_none()
    if row:
        row.name = entry["name"]
        row.description = entry.get("description")
    else:
        row = Concept(
            slug=entry["slug"],
            name=entry["name"],
            description=entry.get("description"),
        )
        db.add(row)
    db.flush()
    return row


def match_songs(
    db: Session,
    keywords: list[str],
    lyrics_terms: list[str] | None = None,
) -> list[Song]:
    """Devuelve canciones cuyo title o slug contiene alguna de las keywords
    (case-insensitive), o cuyo `lyrics_clean` matchea con word boundary
    alguno de los `lyrics_terms` (lookup más cuidadoso para topónimos)."""
    out: list[Song] = []
    seen: set[int] = set()
    for kw in keywords:
        kw_norm = kw.lower()
        rows = db.query(Song).filter(
            (Song.slug.ilike(f"%{kw_norm}%")) | (Song.title.ilike(f"%{kw_norm}%"))
        ).all()
        for s in rows:
            if s.id not in seen:
                seen.add(s.id)
                out.append(s)
    if lyrics_terms:
        for term in lyrics_terms:
            # \m y \M en PostgreSQL = word boundaries (regexp ILIKE no soporta
            # boundary; usamos `~*` con extracto). Escapamos el término
            # mínimamente — solo letras/acentos/espacios habituales.
            pattern = rf"\m{re.escape(term)}\M"
            rows = (
                db.query(Song)
                .filter(Song.lyrics_clean.op("~*")(pattern))
                .all()
            )
            for s in rows:
                if s.id not in seen:
                    seen.add(s.id)
                    out.append(s)
    return out


def link_song_theme(db: Session, song_id: int, theme_id: int) -> bool:
    existing = db.execute(
        select(SongTheme).where(
            SongTheme.song_id == song_id, SongTheme.theme_id == theme_id
        )
    ).scalar_one_or_none()
    if existing:
        return False
    db.add(SongTheme(song_id=song_id, theme_id=theme_id))
    return True


def link_song_place(db: Session, song_id: int, place_id: int) -> bool:
    existing = db.execute(
        select(SongPlace).where(
            SongPlace.song_id == song_id, SongPlace.place_id == place_id
        )
    ).scalar_one_or_none()
    if existing:
        return False
    db.add(SongPlace(song_id=song_id, place_id=place_id))
    return True


def link_song_concept(db: Session, song_id: int, concept_id: int) -> bool:
    existing = db.execute(
        select(SongConcept).where(
            SongConcept.song_id == song_id, SongConcept.concept_id == concept_id
        )
    ).scalar_one_or_none()
    if existing:
        return False
    db.add(SongConcept(song_id=song_id, concept_id=concept_id))
    return True


def main() -> None:
    if not YAML_PATH.exists():
        print(f"ERROR: no se encuentra {YAML_PATH}")
        return

    with YAML_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    with SessionLocal() as db:
        themes_by_slug: dict[str, Theme] = {}
        for t in data.get("themes", []) or []:
            themes_by_slug[t["slug"]] = upsert_theme(db, t)

        places_by_slug: dict[str, Place] = {}
        for p in data.get("places", []) or []:
            places_by_slug[p["slug"]] = upsert_place(db, p)

        concepts_by_slug: dict[str, Concept] = {}
        for c in data.get("concepts", []) or []:
            concepts_by_slug[c["slug"]] = upsert_concept(db, c)

        db.commit()

        matches = data.get("song_matches", {}) or {}
        lyrics_matches = data.get("song_matches_lyrics", {}) or {}

        added_theme = added_place = added_concept = 0

        def _all_slugs(group_a: dict, group_b: dict) -> set[str]:
            return set((group_a or {}).keys()) | set((group_b or {}).keys())

        themes_slugs = _all_slugs(
            matches.get("themes", {}), lyrics_matches.get("themes", {})
        )
        for slug in themes_slugs:
            theme = themes_by_slug.get(slug)
            if not theme:
                continue
            kws = (matches.get("themes", {}) or {}).get(slug, []) or []
            lt = (lyrics_matches.get("themes", {}) or {}).get(slug, []) or []
            for s in match_songs(db, kws, lt):
                if link_song_theme(db, s.id, theme.id):
                    added_theme += 1

        places_slugs = _all_slugs(
            matches.get("places", {}), lyrics_matches.get("places", {})
        )
        for slug in places_slugs:
            place = places_by_slug.get(slug)
            if not place:
                continue
            kws = (matches.get("places", {}) or {}).get(slug, []) or []
            lt = (lyrics_matches.get("places", {}) or {}).get(slug, []) or []
            for s in match_songs(db, kws, lt):
                if link_song_place(db, s.id, place.id):
                    added_place += 1

        concepts_slugs = _all_slugs(
            matches.get("concepts", {}), lyrics_matches.get("concepts", {})
        )
        for slug in concepts_slugs:
            concept = concepts_by_slug.get(slug)
            if not concept:
                continue
            kws = (matches.get("concepts", {}) or {}).get(slug, []) or []
            lt = (lyrics_matches.get("concepts", {}) or {}).get(slug, []) or []
            for s in match_songs(db, kws, lt):
                if link_song_concept(db, s.id, concept.id):
                    added_concept += 1

        db.commit()

        print(f"Themes:   {len(themes_by_slug)}  ({added_theme} song-links nuevos)")
        print(f"Places:   {len(places_by_slug)}  ({added_place} song-links nuevos)")
        print(f"Concepts: {len(concepts_by_slug)}  ({added_concept} song-links nuevos)")


if __name__ == "__main__":
    main()
