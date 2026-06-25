"""Auditoría de RIGOR sobre los posts YA PUBLICADOS.

Pasa el gate editorial (`editorial_review.review`) por cada post publicado:
  - `revise`: lo TENSA (quita relleno/redundancia) y revalida el cache de Next.
  - `reject`: lo DESPUBLICA (status → `pending_review`, sale del sitio público pero
    no se pierde) + avisa al admin. No se borra: queda recuperable en el panel.
  - `pass`: se queda como está.

SIEMPRE probar con --dry-run primero.

Uso:
    python -m scripts.blog.audit_published --dry-run
    python -m scripts.blog.audit_published
    python -m scripts.blog.audit_published --ids 12 34
"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import date

from app.db.models import Post
from app.db.session import SessionLocal
from app.services.editorial_review import review as editorial_review

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _notify_admin(subject: str, text: str) -> None:
    admin_email = os.getenv("ADMIN_EMAIL")
    if not admin_email:
        logger.info("ADMIN: %s — %s", subject, text)
        return
    try:
        from app.services.email import send_email
        send_email(to=admin_email, subject=subject,
                   html=f"<pre style='font-family:monospace'>{text}</pre>", text=text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("aviso admin falló (%s); %s", exc, text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ids", type=int, nargs="*", help="solo estos posts")
    args = parser.parse_args()

    today = date.today()
    stats = {"revisados": 0, "tensados": 0, "despublicados": 0}

    with SessionLocal() as db:
        q = db.query(Post).filter(Post.status == "published")
        if args.ids:
            q = q.filter(Post.id.in_(args.ids))
        posts = q.order_by(Post.id).all()
        logger.info("Posts publicados a auditar: %d", len(posts))

        for post in posts:
            stats["revisados"] += 1
            subject = (post.target_keyword or post.title or "").strip()
            logger.info("[#%s] (%s) %s", post.id, post.kind, post.title)
            if not post.body_md:
                continue

            when = None
            if post.kind == "news" and post.event_date:
                when = "past" if post.event_date < today else "future"
            v = editorial_review(post.body_md, kind=post.kind, subject=subject, event_when=when)

            if v.verdict == "reject":
                stats["despublicados"] += 1
                logger.info("  ✗ DESPUBLICAR (score %d): %s", v.score, "; ".join(v.reasons))
                if not args.dry_run:
                    post.status = "pending_review"
                    db.commit()
                    try:
                        from app.services.publishing import _revalidate_next
                        _revalidate_next(post.slug)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("revalidate falló: %s", exc)
                    _notify_admin(
                        f"⛔ Despublicado por rigor: {post.title}",
                        f"El post /blog/{post.slug} (#{post.id}) no llega al listón "
                        f"(score {v.score}): {'; '.join(v.reasons) or 'genérico/relleno'}. "
                        "Pasa a pendiente de revisión (fuera del sitio público).",
                    )
            elif v.verdict == "revise" and v.tightened_body_md:
                stats["tensados"] += 1
                logger.info("  tensado (score %d)", v.score)
                if not args.dry_run:
                    post.body_md = v.tightened_body_md
                    db.commit()
                    try:
                        from app.services.publishing import _revalidate_next
                        _revalidate_next(post.slug)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("revalidate falló: %s", exc)

    logger.info(
        "Auditoría %s: %d revisados · %d tensados · %d despublicados",
        "[DRY-RUN]" if args.dry_run else "aplicada",
        stats["revisados"], stats["tensados"], stats["despublicados"],
    )


if __name__ == "__main__":
    main()
