"""Publica automáticamente una entrada de efeméride (cumpleaños o aniversario
de fallecimiento) en el blog de Entre Interiores.

Diseñado para ejecutarse desde cron una vez al año en la fecha exacta. El
slug incluye el año, por lo que el script es idempotente: si la entrada de
ese año ya existe, no la duplica ni la sobrescribe.

Tono editorial: cariño, nostalgia y admiración. La plantilla se genera con
el año actual y queda como `draft` para que el admin pueda revisar y
ajustar antes de la publicación efectiva — alternativamente, con la flag
`--publish-now` la marca como `published` en el acto.

Uso:
    python -m scripts.blog.publish_anniversary --type birth
    python -m scripts.blog.publish_anniversary --type death --publish-now

Datos personales (BIRTH_DATE / DEATH_DATE) viven en este fichero para
mantener el cron simple. Si en algún momento cambian, se editan aquí.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone

from sqlalchemy import select

from app.db.models import Post
from app.db.session import SessionLocal

# Fechas reales de la persona. Si DEATH_DATE queda en None, el cron de
# aniversario de muerte no debe correr (y el crontab lo deja desactivado).
BIRTH_DATE = date(1962, 5, 16)
DEATH_DATE: date | None = None

ROBE_FULL_NAME = "Roberto Iniesta"
ROBE_ARTIST_NAME = "Robe"


def years_since(d: date, today: date) -> int:
    years = today.year - d.year
    if (today.month, today.day) < (d.month, d.day):
        years -= 1
    return years


def build_birth_post(today: date) -> dict:
    age_would_be = today.year - BIRTH_DATE.year
    title = f"{age_would_be} velas para Robe ({today.year})"
    slug = f"cumpleanos-robe-{today.year}"
    excerpt = (
        f"El 16 de mayo de {today.year}, Robe cumple "
        f"{age_would_be}. Una nota breve desde el cariño."
    )
    body = (
        f"El **16 de mayo de {today.year}** marca otro cumpleaños de "
        f"**{ROBE_FULL_NAME}**. "
        f"Nacido en {BIRTH_DATE.year} en Plasencia, hoy cumple "
        f"**{age_would_be}** años.\n\n"
        "No hay mucho que añadir a lo que su música ya dice. Solo dejar "
        "constancia, como cada año, de que la fecha está aquí, en el "
        "calendario, y de que sigue mereciendo la pena recordarla.\n\n"
        f"Felicidades, Robe. Donde quiera que estés celebrando.\n\n"
        "— *Entre Interiores*"
    )
    return {
        "slug": slug,
        "kind": "anniversary",
        "title": title,
        "excerpt": excerpt,
        "body_md": body,
        "anniversary_year": today.year,
        "meta_title": f"Cumpleaños de Robe {today.year} · Entre Interiores",
        "meta_description": excerpt,
    }


def build_death_post(today: date) -> dict:
    if DEATH_DATE is None:
        raise SystemExit(
            "DEATH_DATE no está configurado en el script. Si procede activar "
            "este cron, edita publish_anniversary.py y rellena DEATH_DATE."
        )
    years = years_since(DEATH_DATE, today)
    title = f"{years} años sin Robe ({today.year})"
    slug = f"aniversario-robe-{today.year}"
    excerpt = (
        f"El {DEATH_DATE.day} de mayo de {today.year} se cumplen "
        f"{years} años sin Robe. Una nota breve desde el cariño."
    )
    body = (
        f"Hoy se cumplen **{years}** años de la ausencia de "
        f"**{ROBE_FULL_NAME}**. La fecha es de las que se quedan "
        "puestas para siempre.\n\n"
        "No hace falta solemnidad: basta con dejar las canciones puestas "
        "y dejarlas hacer su trabajo. Lo hacen mejor que cualquier texto.\n\n"
        "— *Entre Interiores*"
    )
    return {
        "slug": slug,
        "kind": "anniversary",
        "title": title,
        "excerpt": excerpt,
        "body_md": body,
        "anniversary_year": today.year,
        "meta_title": f"Aniversario de Robe {today.year} · Entre Interiores",
        "meta_description": excerpt,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", choices=["birth", "death"], required=True)
    parser.add_argument(
        "--publish-now",
        action="store_true",
        help="Publica la entrada directamente (status='published'). Sin esto, "
        "queda en 'draft' para revisión manual.",
    )
    parser.add_argument(
        "--date",
        help="Sobrescribe la fecha de hoy (YYYY-MM-DD). Útil para tests.",
    )
    args = parser.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()

    builder = build_birth_post if args.type == "birth" else build_death_post
    payload = builder(today)

    with SessionLocal() as db:
        existing = db.execute(
            select(Post).where(Post.slug == payload["slug"])
        ).scalar_one_or_none()

        if existing:
            print(f"Entrada {payload['slug']} ya existe (status={existing.status}). No se modifica.")
            return

        status = "published" if args.publish_now else "draft"
        published_at = datetime.now(timezone.utc) if args.publish_now else None

        post = Post(
            slug=payload["slug"],
            kind=payload["kind"],
            status=status,
            title=payload["title"],
            excerpt=payload["excerpt"],
            body_md=payload["body_md"],
            meta_title=payload["meta_title"],
            meta_description=payload["meta_description"],
            anniversary_year=payload["anniversary_year"],
            published_at=published_at,
        )
        db.add(post)
        db.commit()

        print(f"Creada entrada {payload['slug']} con status={status}.")
        if status == "draft":
            print("→ Revisa en /biblioteca/admin/seo (próximamente endpoint admin de posts) y publica cuando esté revisada.")


if __name__ == "__main__":
    main()
