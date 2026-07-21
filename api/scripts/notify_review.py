"""Digest diario de "cosas pendientes de revisar" al admin (F2.6).

Reúne todo lo que quedó esperando tu criterio y lo manda en UN email (anti-spam),
con enlaces directos al panel:
  - Erratas de fans que el consenso no pudo resolver solo (needs_human/pending).
  - Posts del blog en pending_review.
  - (informativo) auto-correcciones aplicadas por el MCV en las últimas 24h.

No manda nada si no hay nada pendiente. Cron: diario por la mañana.

Uso:
  python -m scripts.notify_review
  python -m scripts.notify_review --dry-run
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.config import get_settings
from app.db.models import ErrataReport, Post, VerificationRecord
from app.db.session import SessionLocal
from app.services.email import send_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_SITE = "https://entreinteriores.com"


def _gather(db) -> dict:
    erratas = db.execute(
        select(ErrataReport)
        .where(ErrataReport.status.in_(("needs_human", "pending")))
        .order_by(ErrataReport.created_at.desc())
    ).scalars().all()
    posts_pending = db.execute(
        select(func.count()).select_from(Post).where(Post.status == "pending_review")
    ).scalar_one()
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    autofixes = db.execute(
        select(VerificationRecord)
        .where(VerificationRecord.auto_applied.is_(True), VerificationRecord.checked_at >= since)
        .order_by(VerificationRecord.checked_at.desc())
    ).scalars().all()
    return {"erratas": erratas, "posts_pending": int(posts_pending), "autofixes": autofixes}


def _build_html(data: dict) -> str:
    er = data["erratas"]
    parts = ["<h2 style='font-family:Georgia,serif'>Entre Interiores · cosas por revisar</h2>"]

    if er:
        parts.append(f"<h3>Erratas por revisar ({len(er)})</h3><ul>")
        for e in er[:30]:
            wrong = (e.reported_wrong or "")[:120]
            right = (e.suggested_right or "")[:120]
            parts.append(
                f"<li><b>{e.target_type}</b>"
                + (f" · {e.field}" if e.field else "")
                + (f"<br>mal: <i>{wrong}</i>" if wrong else "")
                + (f"<br>debería: <i>{right}</i>" if right else "")
                + f" <span style='color:#888'>({e.reporter or 'anónimo'})</span></li>"
            )
        parts.append("</ul>")
        parts.append(f"<p><a href='{_SITE}/biblioteca/admin/erratas'>→ Gestionar erratas</a></p>")

    if data["posts_pending"]:
        parts.append(f"<h3>Blog en revisión ({data['posts_pending']})</h3>")
        parts.append(f"<p><a href='{_SITE}/biblioteca/admin/blog'>→ Revisar el blog</a></p>")

    if data["autofixes"]:
        parts.append(f"<h3>Auto-correcciones (últimas 24h): {len(data['autofixes'])}</h3><ul>")
        for v in data["autofixes"][:15]:
            old = (v.old_value or "")[:60]
            new = (v.new_value or "")[:60]
            parts.append(f"<li>{v.claim_kind}: <s style='color:#999'>{old}</s> → <b>{new}</b> "
                         f"<span style='color:#888'>(conf {v.confidence:.2f})</span></li>")
        parts.append("</ul>")
        parts.append(f"<p><a href='{_SITE}/biblioteca/admin/erratas'>→ Feed de auditoría</a></p>")

    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description="Digest diario de revisión al admin.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    settings = get_settings()
    to = settings.admin_email
    if not to:
        logger.warning("Sin ADMIN_EMAIL configurado; no se envía.")
        return

    db = SessionLocal()
    try:
        data = _gather(db)
    finally:
        db.close()

    n_er = len(data["erratas"])
    if not (n_er or data["posts_pending"]):
        logger.info("Nada pendiente de revisar; no se envía email.")
        return

    subject = f"[Entre Interiores] {n_er} errata(s) y {data['posts_pending']} post(s) por revisar"
    html = _build_html(data)
    if args.dry_run:
        logger.info("(dry-run) enviaría a %s: %s", to, subject)
        logger.info(html[:500])
        return
    mid = send_email(to, subject, html)
    logger.info("Digest enviado a %s (id=%s)", to, mid)


if __name__ == "__main__":
    main()
