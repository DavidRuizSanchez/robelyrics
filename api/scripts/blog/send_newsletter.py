"""Dispatcher semanal de la newsletter de Entre Interiores.

Workflow:
  1. Busca posts publicados en los últimos N días (default 7) con
     `newsletter_sent_at IS NULL`.
  2. Si no hay nada, sale sin enviar.
  3. Construye un digest HTML/text con esas entradas.
  4. Itera subscribers `status='confirmed'` y envía a cada uno con su
     `unsubscribe_token` personal en el link de baja del footer.
  5. Marca los posts con `newsletter_sent_at` y los subscribers con
     `last_sent_at`. Reenviar el mismo cron sin posts nuevos no envía nada.

Diseñado para correr semanalmente vía cron en el host:
    0 10 * * 1 cd /opt/robelyrics && docker compose exec -T api \
        python -m scripts.blog.send_newsletter

Flags útiles:
  --dry-run                  Solo lista qué se enviaría.
  --window-days N            Mira posts de los últimos N días (default 7).
  --only-email a@b.com       Solo envía a un destinatario concreto (test).
  --include-post-ids 12,13   Fuerza inclusión de IDs concretos.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models import Post, Subscriber
from app.db.session import SessionLocal
from app.services.email import (
    EmailError,
    render_newsletter_digest_email,
    send_email,
)

logger = logging.getLogger(__name__)

KIND_LABEL = {
    "editorial": "Editorial",
    "news": "Noticia",
    "anniversary": "Efeméride",
}


def site_url() -> str:
    return os.environ.get("SITE_URL", "https://entreinteriores.com").rstrip("/")


def format_date(dt: datetime) -> str:
    months = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    return f"{dt.day} de {months[dt.month - 1]} de {dt.year}"


def collect_posts(db, window_days: int, include_ids: list[int]) -> list[Post]:
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    base_q = (
        db.query(Post)
        .filter(Post.status == "published")
        .filter(Post.newsletter_sent_at.is_(None))
        .filter(Post.published_at >= since)
        .order_by(Post.published_at.desc())
    )
    posts = list(base_q.all())
    if include_ids:
        extra = db.query(Post).filter(Post.id.in_(include_ids)).all()
        seen = {p.id for p in posts}
        for p in extra:
            if p.id not in seen:
                posts.append(p)
    return posts


def post_to_dict(p: Post, base_url: str) -> dict:
    return {
        "title": p.title,
        "excerpt": p.excerpt,
        "url": f"{base_url}/blog/{p.slug}",
        "kind_label": KIND_LABEL.get(p.kind, p.kind),
        "published_at_human": format_date(p.published_at) if p.published_at else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--only-email", default=None)
    parser.add_argument(
        "--include-post-ids",
        default="",
        help="Lista de IDs de Post separados por coma; se incluyen aunque "
        "estén fuera de la ventana o ya marcados como enviados.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    include_ids = [int(x) for x in args.include_post_ids.split(",") if x.strip()]
    base_url = site_url()

    with SessionLocal() as db:
        posts = collect_posts(db, args.window_days, include_ids)
        if not posts:
            logger.info(
                "Sin posts publicados en los últimos %d días sin enviar. Nada que hacer.",
                args.window_days,
            )
            return 0

        post_dicts = [post_to_dict(p, base_url) for p in posts]
        logger.info("Posts a enviar: %d", len(post_dicts))
        for pd in post_dicts:
            logger.info("  · %s — %s", pd["kind_label"], pd["title"])

        sub_q = db.query(Subscriber).filter(Subscriber.status == "confirmed")
        if args.only_email:
            sub_q = sub_q.filter(Subscriber.email == args.only_email.lower())
        subscribers = list(sub_q.all())
        logger.info("Suscriptores confirmados destino: %d", len(subscribers))

        if args.dry_run:
            logger.info("dry-run: nada se envía y posts NO se marcan.")
            return 0

        if not subscribers:
            logger.info("Sin destinatarios. No marcamos posts como enviados.")
            return 0

        subject = (
            f"Una entrada nueva · {post_dicts[0]['title']}"
            if len(post_dicts) == 1
            else f"{len(post_dicts)} entradas nuevas en Entre Interiores"
        )

        sent_ok = 0
        sent_failed = 0
        now = datetime.now(timezone.utc)

        for sub in subscribers:
            unsubscribe_url = (
                f"{base_url}/newsletter/baja?token={sub.unsubscribe_token}"
            )
            html, text = render_newsletter_digest_email(
                post_dicts, unsubscribe_url, base_url
            )
            try:
                send_email(to=sub.email, subject=subject, html=html, text=text)
                sub.last_sent_at = now
                sent_ok += 1
            except EmailError as e:
                logger.warning("Send failed for %s: %s", sub.email, e)
                sent_failed += 1

        # Solo marcamos los posts si al menos un envío salió OK.
        if sent_ok > 0 and not args.only_email and not include_ids:
            for p in posts:
                p.newsletter_sent_at = now

        db.commit()

        logger.info("Envíos OK: %d · fallidos: %d", sent_ok, sent_failed)
        if sent_failed and not sent_ok:
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
