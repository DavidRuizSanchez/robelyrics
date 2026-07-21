"""Auditoría factual retroactiva de TODO el contenido público.

Recorre el contenido ya publicado, extrae sus afirmaciones, las valida en
cascada (BD → corpus → Wikipedia/Google) y AUTO-CORRIGE in-place lo que esté
mal, manteniéndolo publicado (decisión de producto). Deja un informe CSV con
cada corrección para trazabilidad.

Tipos de contenido:
  - seo:           SeoContent.body_md (published=True) — páginas de entidad.
  - post:          Post.body_md (status='published') — blog/noticias.
  - book:          Book.body_md/summary — fichas curadas (sobre todo DETECTA).
  - interpretation: SongInterpretation.payload (fan_consensus) — solo hechos duros.
  - instagram:     InstagramQueueItem.caption (status='published').

Idempotente: una segunda pasada sobre contenido ya corregido no cambia nada.
La caché de web_verify (/tmp) evita repetir verificaciones web entre items.

Uso:
    python -m scripts.audit.fact_audit --type all --dry-run --out report.csv
    python -m scripts.audit.fact_audit --type post
    python -m scripts.audit.fact_audit --type seo --limit 20
    python -m scripts.audit.fact_audit --type post --slug robe-entre-libros-y-reflexiones
"""
from __future__ import annotations

import argparse
import csv
import logging
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select

from app.db.session import SessionLocal
from app.services.fact_check import (
    CatalogIndex,
    FactCheckReport,
    build_catalog_index,
    check_body,
    correct_body,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fact_audit")

TYPES = ("seo", "post", "book", "interpretation", "instagram")


@dataclass
class Item:
    content_type: str
    id: int
    slug: str
    get_text: Callable[[], str]              # lee el texto actual
    set_text: Callable[[str], None]          # escribe el texto corregido (en el objeto ORM)
    material: str = ""                       # grounding para el corrector
    on_corrected: Callable[[], None] | None = None  # hook tras commit (revalidate Next)


# --------------------------------------------------------------------------- #
# Material (grounding) por tipo — best-effort
# --------------------------------------------------------------------------- #
def _material_for_seo(db, sc) -> str:
    """Reconstruye el contexto documentado de una página de entidad."""
    from scripts.blog.context_builder import (
        album_context,
        artist_context,
        song_context,
        taxonomy_context,
    )
    try:
        et, eid = sc.entity_type, sc.entity_id
        if et == "song":
            return song_context(db, eid)
        if et == "album":
            return album_context(db, eid)
        if et == "artist":
            return artist_context(db, eid)
        if et in ("theme", "place", "concept"):
            return taxonomy_context(db, None, sc.body_md[:1500])
    except Exception as exc:  # noqa: BLE001
        logger.warning("material seo %s/%s falló: %s", sc.entity_type, sc.entity_id, exc)
    return ""


# --------------------------------------------------------------------------- #
# Recolectores de items por tipo
# --------------------------------------------------------------------------- #
def _collect_posts(db, *, slug: str | None, limit: int | None) -> list[Item]:
    from app.db.models import Post
    from app.services.publishing import _revalidate_next
    q = select(Post).where(Post.status == "published")
    if slug:
        q = q.where(Post.slug == slug)
    q = q.order_by(Post.id)
    if limit:
        q = q.limit(limit)
    items: list[Item] = []
    for p in db.execute(q).scalars().all():
        def _mk(post):
            return Item(
                content_type="post", id=post.id, slug=post.slug,
                get_text=lambda: post.body_md or "",
                set_text=lambda v: setattr(post, "body_md", v),
                material="",
                on_corrected=lambda: _revalidate_next(post.slug),
            )
        items.append(_mk(p))
    return items


def _collect_seo(db, *, slug: str | None, limit: int | None) -> list[Item]:
    from app.db.models import SeoContent
    q = select(SeoContent).where(SeoContent.published.is_(True))
    if slug:
        q = q.where(SeoContent.slug == slug)
    q = q.order_by(SeoContent.id)
    if limit:
        q = q.limit(limit)
    items: list[Item] = []
    for sc in db.execute(q).scalars().all():
        def _mk(row):
            return Item(
                content_type="seo", id=row.id, slug=row.slug,
                get_text=lambda: row.body_md or "",
                set_text=lambda v: setattr(row, "body_md", v),
                material=_material_for_seo(db, row),
            )
        items.append(_mk(sc))
    return items


def _collect_books(db, *, slug: str | None, limit: int | None) -> list[Item]:
    from app.db.models import Book
    q = select(Book)
    if slug:
        q = q.where(Book.slug == slug)
    q = q.order_by(Book.id)
    if limit:
        q = q.limit(limit)
    items: list[Item] = []
    for b in db.execute(q).scalars().all():
        if not (b.body_md or "").strip():
            continue
        def _mk(row):
            return Item(
                content_type="book", id=row.id, slug=row.slug,
                get_text=lambda: row.body_md or "",
                set_text=lambda v: setattr(row, "body_md", v),
                material=(row.summary or ""),
            )
        items.append(_mk(b))
    return items


def _collect_instagram(db, *, slug: str | None, limit: int | None) -> list[Item]:
    from app.db.models import InstagramQueueItem
    q = select(InstagramQueueItem).where(InstagramQueueItem.status == "published")
    q = q.order_by(InstagramQueueItem.id)
    if limit:
        q = q.limit(limit)
    items: list[Item] = []
    for it in db.execute(q).scalars().all():
        if not (it.caption or "").strip():
            continue
        def _mk(row):
            return Item(
                content_type="instagram", id=row.id, slug=str(row.id),
                get_text=lambda: row.caption or "",
                set_text=lambda v: setattr(row, "caption", v),
            )
        items.append(_mk(it))
    return items


COLLECTORS = {
    "post": _collect_posts,
    "seo": _collect_seo,
    "book": _collect_books,
    "instagram": _collect_instagram,
}


# --------------------------------------------------------------------------- #
# Núcleo
# --------------------------------------------------------------------------- #
def _snippet(text: str, quote: str, width: int = 140) -> str:
    if not quote:
        return text[:width].replace("\n", " ")
    idx = text.find(quote)
    if idx < 0:
        return quote[:width]
    start = max(0, idx - 20)
    return text[start:idx + len(quote) + 20].replace("\n", " ")


def _audit_item(
    db, item: Item, index: CatalogIndex, *, dry_run: bool, use_web: bool,
    writer: csv.writer | None,
) -> tuple[int, int, int]:
    """Audita un item. Devuelve (evaluadas, auto-corregidas, a_revisar)."""
    body = item.get_text()
    if not body.strip():
        return 0, 0, 0
    report: FactCheckReport = check_body(
        db, body, material=item.material, index=index, use_web=use_web
    )
    n_eval = len(report.verdicts)
    autofixes = report.autofixes      # refutados con evidencia → se corrigen
    to_review = report.to_review      # no verificables → solo se reportan

    # GATE DE CITAS DE LETRA (determinista): detecta versos inventados o citas de
    # canciones sin letra verificable en contenido YA publicado. No se auto-borran
    # (requieren reescritura); se reportan al CSV como revisión.
    lyric_issues: list = []
    if item.content_type in ("post", "seo", "interpretation"):
        try:
            from app.services.lyric_guard import check_lyrics
            lr = check_lyrics(db, body)
            lyric_issues = lr.blocking + lr.to_review
        except Exception as exc:  # noqa: BLE001
            logger.warning("lyric-guard %s/%s falló: %s", item.content_type, item.id, exc)

    if not autofixes and not to_review and not lyric_issues:
        return n_eval, 0, 0

    before = body
    fixed = body
    skipped: list = []
    if not autofixes and not to_review and lyric_issues:
        # Solo hay citas de letra que revisar (nada que corregir contra BD).
        for lv in lyric_issues:
            logger.info("  [%s/%s] CITA %s: «%s» — %s",
                        item.content_type, item.slug, lv.status, lv.quote[:60], lv.reason)
            if writer:
                writer.writerow([
                    item.content_type, item.id, item.slug, f"lyric:{lv.status}", "revisar",
                    lv.attributed_song or "", lv.quote, lv.matched_song or "", "lyrics",
                    lv.reason, _snippet(before, lv.quote), "(sin tocar)",
                ])
        return n_eval, 0, len(lyric_issues)
    # Corrección quirúrgica determinista (también en dry-run, en memoria, para el
    # preview del antes/después; solo se escribe en BD si no es dry-run).
    fixed, skipped = correct_body(db, before, report, index=index, material=item.material)
    skipped_ids = {id(v) for v in skipped}
    if not dry_run and fixed and fixed != before:
        item.set_text(fixed)
        db.commit()
        if item.on_corrected:
            try:
                item.on_corrected()
            except Exception as exc:  # noqa: BLE001
                logger.warning("on_corrected %s/%s falló: %s", item.content_type, item.id, exc)

    corrected = [v for v in autofixes if id(v) not in skipped_ids]
    for v in corrected:
        c = v.claim
        logger.info(
            "  [%s/%s] CORRIGE %s → %s (%s)",
            item.content_type, item.slug, c.type,
            (v.correct_value or "ELIMINAR"), v.source or "?",
        )
        if writer:
            writer.writerow([
                item.content_type, item.id, item.slug, c.type, "corregido",
                c.subject, c.object, v.correct_value or "ELIMINAR", v.source, v.evidence,
                _snippet(before, c.quote), _snippet(fixed, c.quote),
            ])
    # No corregibles de forma quirúrgica (requieren reformular) + dudosos web → revisión.
    for v in list(skipped) + list(to_review):
        c = v.claim
        logger.info("  [%s/%s] REVISAR %s · %s (%s)",
                    item.content_type, item.slug, c.type, c.subject,
                    "no-quirurgico" if id(v) in skipped_ids else "web")
        if writer:
            writer.writerow([
                item.content_type, item.id, item.slug, c.type, "revisar",
                c.subject, c.object, v.correct_value or "", v.source, v.evidence,
                _snippet(before, c.quote), "(sin tocar)",
            ])
    # Citas de letra inventadas / no verificables (reescritura manual).
    for lv in lyric_issues:
        logger.info("  [%s/%s] CITA %s: «%s» — %s",
                    item.content_type, item.slug, lv.status, lv.quote[:60], lv.reason)
        if writer:
            writer.writerow([
                item.content_type, item.id, item.slug, f"lyric:{lv.status}", "revisar",
                lv.attributed_song or "", lv.quote, lv.matched_song or "", "lyrics",
                lv.reason, _snippet(before, lv.quote), "(sin tocar)",
            ])
    return n_eval, len(corrected), len(skipped) + len(to_review) + len(lyric_issues)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", choices=("all", *TYPES), default="all")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe BD; solo informa de lo que corregiría.")
    parser.add_argument("--web", action="store_true",
                        help="Activa verificación web (Wikipedia/Google) para "
                             "señalar candidatos a revisión. NO auto-borra; solo "
                             "reporta. Por defecto solo se valida contra BD.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--slug", default=None, help="Filtra por slug (post/seo/book).")
    parser.add_argument("--out", default=None, help="Ruta del CSV de informe.")
    args = parser.parse_args()

    types = list(TYPES) if args.type == "all" else [args.type]
    # interpretation se trata aparte (payload JSON), de momento fuera del barrido
    # automático para no tocar interpretación fan; se audita con cuidado a mano.
    types = [t for t in types if t in COLLECTORS]

    out_fh = open(args.out, "w", newline="", encoding="utf-8") if args.out else None
    writer = csv.writer(out_fh) if out_fh else None
    if writer:
        writer.writerow([
            "content_type", "id", "slug", "claim_type", "status",
            "subject", "object", "correct_value", "source", "evidence",
            "before", "after",
        ])

    total_items = total_eval = total_corr = total_review = items_touched = 0
    with SessionLocal() as db:
        logger.info("Construyendo índice de catálogo…")
        index = build_catalog_index(db)
        logger.info("Índice: %d canciones · %d álbumes · %d libros",
                    len(index.songs), len(index.albums), len(index.book_titles))

        for t in types:
            items = COLLECTORS[t](db, slug=args.slug, limit=args.limit)
            logger.info("[%s] %d items %s", t, len(items),
                        "(dry-run)" if args.dry_run else "")
            for item in items:
                total_items += 1
                n_eval, n_corr, n_rev = _audit_item(
                    db, item, index, dry_run=args.dry_run, use_web=args.web, writer=writer
                )
                total_eval += n_eval
                total_corr += n_corr
                total_review += n_rev
                if n_corr or n_rev:
                    items_touched += 1

    if out_fh:
        out_fh.close()
        logger.info("Informe escrito en %s", args.out)

    logger.info(
        "RESUMEN: %d items · %d afirmaciones · %d auto-corregidas · %d a revisar "
        "(%d items afectados)%s",
        total_items, total_eval, total_corr, total_review, items_touched,
        " · DRY-RUN, nada escrito" if args.dry_run else "",
    )


if __name__ == "__main__":
    main()
