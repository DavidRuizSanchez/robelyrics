"""Siembra/actualiza la tabla `books` desde data/books.yaml (sección /libros).

Idempotente por slug: hace upsert de los metadatos bibliográficos y la ficha
curada. Si un libro trae `cover_url` externa, la re-aloja en Cloudinary (dominio
permitido por next/image) salvo que ya esté en Cloudinary.

REGLAS QUE SE APLICAN EN CADA SEED (red de seguridad — el contenido de libros
se escribe a mano en el YAML y NO pasa por el pipeline LLM, así que aquí
replicamos sus controles):
  1. Anti em-dash: todo campo de texto pasa por `strip_ai_tells` (— – ― → coma).
  2. Headings: `body_md` se normaliza para empezar en H2 (`normalize_headings`).
  3. H1 anti-canibalización: el título no puede ser un término reservado del
     core (extremoduro / robe) ni empezar por él a secas, para no competir con
     /extremoduro y /robe. Debe ser descriptivo (incluir colección/subtítulo).
  4. SEO mínimos: summary + meta_title + meta_description obligatorios; avisos
     de longitud (meta_title ~60, meta_description ~160).
Un libro que incumpla 3 o 4 (faltas duras) se RECHAZA y no se siembra.

Uso:
    python -m scripts.seed_books [--slug X] [--no-rehost]
"""
from __future__ import annotations

import argparse
import os

import yaml
from sqlalchemy import select

from app.db.models import Book
from app.services.text_sanitizer import normalize_headings, strip_ai_tells
from scripts.research.common import get_session, log

_FIELDS = (
    "title", "subtitle", "authors", "year", "publisher", "isbn", "pages",
    "language", "kind", "availability", "cover_attribution", "summary",
    "body_md", "buy_links", "about", "meta_title", "meta_description",
    "sort_order",
)

# Campos de texto libre que se sanean (anti em-dash) en cada seed.
_TEXT_FIELDS = ("title", "subtitle", "summary", "body_md", "meta_title", "meta_description")

# Términos reservados del core: un H1/título de libro NO puede ser esto a secas
# (canibalizaría /extremoduro y /robe). Debe ser descriptivo.
_RESERVED_H1 = {"extremoduro", "robe", "robe iniesta", "roberto iniesta"}


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


def _clean_entry(e: dict) -> dict:
    """Sanea campos de texto y normaliza headings. Devuelve copia limpia."""
    out = dict(e)
    for f in _TEXT_FIELDS:
        if out.get(f):
            out[f] = strip_ai_tells(out[f])
    if out.get("body_md"):
        out["body_md"] = normalize_headings(out["body_md"])
    return out


def _hard_errors(e: dict) -> list[str]:
    """Faltas que impiden sembrar el libro (devuelve lista de mensajes)."""
    errs: list[str] = []
    title = (e.get("title") or "").strip()
    if not title:
        errs.append("sin título")
    elif title.lower() in _RESERVED_H1:
        errs.append(
            f"título '{title}' canibaliza una URL del core; usa un título "
            f"descriptivo (incluye colección/subtítulo)"
        )
    if not (e.get("summary") or "").strip():
        errs.append("sin summary (resumen obligatorio)")
    if not (e.get("meta_title") or "").strip():
        errs.append("sin meta_title")
    if not (e.get("meta_description") or "").strip():
        errs.append("sin meta_description")
    return errs


def _soft_warnings(e: dict) -> list[str]:
    warns: list[str] = []
    mt = e.get("meta_title") or ""
    md = e.get("meta_description") or ""
    if len(mt) > 70:
        warns.append(f"meta_title {len(mt)} chars (>70)")
    if len(md) > 165:
        warns.append(f"meta_description {len(md)} chars (>165)")
    body = e.get("body_md") or ""
    if "# " in body and not body.lstrip().startswith("## "):
        warns.append("body_md no empieza en H2")
    return warns


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
    created = updated = rejected = 0
    with get_session() as db:
        for raw in entries:
            slug = raw.get("slug")
            if not slug:
                continue
            if args.slug and slug != args.slug:
                continue

            e = _clean_entry(raw)

            errs = _hard_errors(e)
            if errs:
                for msg in errs:
                    log(f"  ✗ {slug}: {msg}", "err")
                rejected += 1
                continue
            for w in _soft_warnings(e):
                log(f"  ! {slug}: {w}", "warn")

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
    log(
        f"Libros: {created} creados · {updated} actualizados · {rejected} rechazados",
        "err" if rejected else "ok",
    )


if __name__ == "__main__":
    main()
