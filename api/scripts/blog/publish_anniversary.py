"""Publica una efeméride personal de Robe (cumpleaños o aniversario de muerte).

Para ejecutarse desde cron en la fecha exacta. Idempotente por slug
(`cumpleanos-robe-YYYY` / `aniversario-robe-YYYY`).

El texto se genera con `content_generator.generate_anniversary` cada año,
con contexto del momento, para que la pieza sea diferente cada vez. La
imagen heroica se busca en Wikimedia Commons. Estas piezas son **excepción
al cap de 2/semana**: kind='anniversary' siempre publica el día exacto.

Uso:
    python -m scripts.blog.publish_anniversary --type birth
    python -m scripts.blog.publish_anniversary --type death
    python -m scripts.blog.publish_anniversary --type death --dry-run
    python -m scripts.blog.publish_anniversary --type birth --date 2027-05-16

Datos personales (BIRTH_DATE / DEATH_DATE) viven en este fichero para que el
cron sea simple. Si cambian, se editan aquí.
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

from sqlalchemy import select

from app.db.models import Post
from app.db.session import SessionLocal
from app.services.content_generator import generate_anniversary
from app.services.publishing import propose_for_review
from app.services.wikimedia import search_image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BIRTH_DATE = date(1962, 5, 16)
DEATH_DATE: date | None = date(2025, 12, 10)

ROBE_NAME = "Robe Iniesta"


def _years_since(d: date, today: date) -> int:
    years = today.year - d.year
    if (today.month, today.day) < (d.month, d.day):
        years -= 1
    return years


def _slug_for(kind: str, year: int) -> str:
    return (
        f"cumpleanos-robe-{year}" if kind == "birth" else f"aniversario-robe-{year}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", choices=["birth", "death"], required=True)
    parser.add_argument(
        "--date",
        help="Sobrescribe la fecha de hoy (YYYY-MM-DD). Útil para tests.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Genera el texto e imprime sin tocar la DB.",
    )
    parser.add_argument(
        "--no-image",
        action="store_true",
        help="Salta la búsqueda de imagen Wikimedia (más rápido para tests).",
    )
    parser.add_argument(
        "--context",
        help="Nota de contexto adicional para el LLM (opcional).",
    )
    args = parser.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()

    if args.type == "death":
        if DEATH_DATE is None:
            raise SystemExit("DEATH_DATE no configurado en publish_anniversary.py")
        years = _years_since(DEATH_DATE, today)
    else:
        years = today.year - BIRTH_DATE.year

    slug = _slug_for(args.type, today.year)
    logger.info("Generando efeméride %s para %s (slug=%s)", args.type, today, slug)

    # Idempotencia: si ya existe el slug, no se sobrescribe
    if not args.dry_run:
        with SessionLocal() as db:
            existing = db.execute(
                select(Post).where(Post.slug == slug)
            ).scalar_one_or_none()
            if existing is not None:
                logger.info(
                    "Post %s ya existe (status=%s) — no se modifica",
                    slug, existing.status,
                )
                return

    payload = generate_anniversary(
        args.type,
        person_name=ROBE_NAME,
        years_since=years,
        today=today,
        context_notes=args.context,
    )

    img = None
    if not args.no_image:
        img = search_image(ROBE_NAME)
        if img:
            logger.info(
                "Imagen Wikimedia: %s (license=%s)",
                img.source_page_url, img.license_short,
            )
        else:
            logger.info("Sin imagen Wikimedia disponible para %s", ROBE_NAME)

    if args.dry_run:
        print("\n=== DRY RUN ===")
        print("slug:", slug)
        print("title:", payload["title"])
        print("excerpt:", payload["excerpt"])
        print("meta_title:", payload["meta_title"])
        print("meta_description:", payload["meta_description"])
        if img:
            print("hero_image_url:", img.thumb_url)
            print("attribution:", img.attribution_text)
        print("---BODY---")
        print(payload["body_md"])
        print("=== END DRY RUN ===\n")
        return

    body_md = payload["body_md"]
    if img:
        body_md = body_md.rstrip() + "\n\n" + img.attribution_text + "\n"

    with SessionLocal() as db:
        post = Post(
            slug=slug,
            kind="anniversary",
            status="draft",  # publishing.schedule_or_publish lo promueve
            title=payload["title"],
            excerpt=payload["excerpt"],
            body_md=body_md,
            meta_title=payload["meta_title"],
            meta_description=payload["meta_description"],
            anniversary_year=today.year,
            hero_image_url=img.thumb_url if img else None,
            hero_image_attribution=img.attribution_text if img else None,
            hero_image_license=img.license_short if img else None,
            hero_image_source_url=img.source_page_url if img else None,
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        # Crea como pending_review. El email consolidado se envía desde
        # ensure_weekly_minimum o desde el endpoint de notify-pending.
        result = propose_for_review(db, post, notify=False)
        logger.info("Resultado publishing: %s", result)


if __name__ == "__main__":
    main()
