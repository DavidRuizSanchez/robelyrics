"""Siembra/actualiza la tabla `books` desde data/books.yaml (sección /libros).

Idempotente por slug: hace upsert de los metadatos bibliográficos y la ficha
curada. Si un libro trae `cover_url` externa, la re-aloja en Cloudinary (dominio
permitido por next/image) salvo que ya esté en Cloudinary.

Uso:
    python -m scripts.seed_books [--slug X] [--no-rehost]
"""
from __future__ import annotations

import argparse
import os

import yaml
from sqlalchemy import select

from app.db.models import Book
from scripts.research.common import get_session, log

_FIELDS = (
    "title", "subtitle", "authors", "year", "publisher", "isbn", "pages",
    "language", "kind", "availability", "cover_attribution", "summary",
    "body_md", "buy_links", "about", "meta_title", "meta_description",
    "sort_order",
)


def _yaml_path() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (
        "/app/data/books.yaml",
        os.path.normpath(os.path.join(here, "..", "..", "data", "books.yaml")),
        os.path.normpath(os.path.join(here, "..", "data", "books.yaml")),
    ):
        if os.path.exists(p):
            return p
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", help="solo un slug")
    ap.add_argument("--no-rehost", action="store_true", help="no re-alojar portadas en Cloudinary")
    args = ap.parse_args()

    path = _yaml_path()
    if not path:
        log("data/books.yaml no encontrado", "err")
        return
    entries = (yaml.safe_load(open(path, encoding="utf-8")) or {}).get("books") or []
    created = updated = 0
    with get_session() as db:
        for e in entries:
            slug = e.get("slug")
            if not slug:
                continue
            if args.slug and slug != args.slug:
                continue
            book = db.execute(select(Book).where(Book.slug == slug)).scalar_one_or_none()
            is_new = book is None
            if is_new:
                book = Book(slug=slug)
                db.add(book)

            for f in _FIELDS:
                if f in e and e[f] is not None:
                    setattr(book, f, e[f])

            # Portada: re-alojar a Cloudinary si es externa.
            cover = e.get("cover_url")
            if cover and not args.no_rehost and "res.cloudinary.com" not in cover:
                # Import perezoso: la cadena de fetch_entity_images es pesada
                # (openai, etc.); solo la cargamos si de verdad hay portada que
                # re-alojar.
                from scripts.seo.fetch_entity_images import _rehost_to_cloudinary
                rehosted = _rehost_to_cloudinary(cover)
                if rehosted:
                    book.cover_url = rehosted
                else:
                    log(f"  fallo re-alojando portada de {slug}", "warn")
                    book.cover_url = cover
            elif cover:
                book.cover_url = cover

            created += 1 if is_new else 0
            updated += 0 if is_new else 1
            log(f"  {'+' if is_new else '~'} {slug}", "ok")
        db.commit()
    log(f"Libros: {created} creados · {updated} actualizados", "ok")


if __name__ == "__main__":
    main()
