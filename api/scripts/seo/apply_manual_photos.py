"""Aplica fotos manuales (URLs externas) re-alojándolas en Cloudinary.

Lee data/manual_photos.yaml con entradas:
  - slug: <slug de persona o álbum>
    url: <URL externa de la imagen>
    kind: person | album        # default person
    attribution: <texto crédito opcional>

Descarga cada imagen y la re-aloja en Cloudinary (dominio permitido por
next/image), luego setea persons.image_url / albums.cover_url. Idempotente:
salta las que ya tienen imagen salvo --force.

Uso:
    python -m scripts.seo.apply_manual_photos [--force] [--slug X]
"""
from __future__ import annotations

import argparse
import os

import yaml
from sqlalchemy import select

from app.db.models import Album, Person
from scripts.research.common import get_session, log
from scripts.seo.fetch_entity_images import _rehost_to_cloudinary


def _yaml_path() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (
        "/app/data/manual_photos.yaml",
        os.path.normpath(os.path.join(here, "..", "..", "..", "data", "manual_photos.yaml")),
        os.path.normpath(os.path.join(here, "..", "..", "data", "manual_photos.yaml")),
    ):
        if os.path.exists(p):
            return p
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-aloja aunque ya tenga imagen")
    ap.add_argument("--slug", help="solo un slug")
    args = ap.parse_args()

    path = _yaml_path()
    if not path:
        log("data/manual_photos.yaml no encontrado", "err")
        return
    entries = (yaml.safe_load(open(path, encoding="utf-8")) or {}).get("photos") or []
    done = skipped = failed = 0
    with get_session() as db:
        for e in entries:
            slug = e.get("slug")
            url = e.get("url")
            kind = e.get("kind", "person")
            if not (slug and url):
                continue
            if args.slug and slug != args.slug:
                continue
            model = Person if kind == "person" else Album
            field = "image_url" if kind == "person" else "cover_url"
            row = db.execute(select(model).where(model.slug == slug)).scalar_one_or_none()
            if not row:
                log(f"  {kind} '{slug}' no encontrado", "warn")
                failed += 1
                continue
            if getattr(row, field) and not args.force:
                skipped += 1
                continue
            rehosted = _rehost_to_cloudinary(url)
            if not rehosted:
                log(f"  fallo re-alojando {slug} ({url[:60]}…)", "warn")
                failed += 1
                continue
            setattr(row, field, rehosted)
            attr = e.get("attribution")
            if attr and hasattr(row, "image_attribution"):
                row.image_attribution = attr
            done += 1
            log(f"  ✓ {kind}/{slug} -> {rehosted}", "ok")
        db.commit()
    log(f"Fotos manuales: {done} aplicadas · {skipped} ya tenían · {failed} fallos", "ok")


if __name__ == "__main__":
    main()
