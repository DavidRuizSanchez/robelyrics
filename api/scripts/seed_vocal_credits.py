"""Siembra los créditos de coros y voces de `data/vocal_credits.yaml`.

Interpretación, no autoría (ver `app.services.credit_roles`). Idempotente: la
clave única (song_id, credit_role, credited_name) de `song_credits` evita
duplicados, y si la persona ya tiene ficha se enlaza con `person_id`. Una canción
que no se encuentra se avisa y se salta: nunca se adivina.

Uso:  python -m scripts.seed_vocal_credits [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml
from sqlalchemy import select

from app.db.models import Album, Person, Song, SongCredit
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("seed_vocal_credits")


def _yaml_path() -> Path:
    for base in (Path("/app/data"), Path(__file__).resolve().parents[2] / "data"):
        if (base / "vocal_credits.yaml").exists():
            return base / "vocal_credits.yaml"
    raise FileNotFoundError("data/vocal_credits.yaml")


def sembrar(db, entradas: list[dict], *, dry_run: bool = False) -> dict[str, int]:
    personas = {}
    for p in db.query(Person).all():
        for nm in (p.stage_name, p.full_name):
            if nm:
                personas[nm.strip().lower()] = p.id
    cuenta = {"insertados": 0, "ya_estaban": 0, "canciones_no_encontradas": 0}
    for e in entradas:
        for song_slug in e["songs"]:
            song = db.execute(
                select(Song).join(Album, Song.album_id == Album.id)
                .where(Album.slug == e["album_slug"], Song.slug == song_slug)
            ).scalar_one_or_none()
            if song is None:
                log.warning("no encuentro %s/%s: se salta", e["album_slug"], song_slug)
                cuenta["canciones_no_encontradas"] += 1
                continue
            for nombre in e["names"]:
                existe = db.execute(select(SongCredit.id).where(
                    SongCredit.song_id == song.id,
                    SongCredit.credit_role == e["role"],
                    SongCredit.credited_name == nombre,
                )).first()
                if existe:
                    cuenta["ya_estaban"] += 1
                    continue
                log.info("%s · %s: %s", song.title, e["role"], nombre)
                cuenta["insertados"] += 1
                if not dry_run:
                    db.add(SongCredit(
                        song_id=song.id, person_id=personas.get(nombre.lower()),
                        credit_role=e["role"], credited_name=nombre, is_primary=False,
                        note=f"Wikipedia: {e['literal']}", source="wikipedia", confidence=1.0,
                    ))
    if not dry_run:
        db.commit()
    return cuenta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    entradas = yaml.safe_load(_yaml_path().read_text(encoding="utf-8"))["credits"]
    with SessionLocal() as db:
        print(sembrar(db, entradas, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
