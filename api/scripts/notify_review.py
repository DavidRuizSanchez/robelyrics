"""Digest diario de "cosas pendientes de revisar" al admin (F2.6).

Reúne todo lo que quedó esperando tu criterio y lo manda en UN email (anti-spam),
con enlaces directos al panel:
  - Erratas de fans que el consenso no pudo resolver solo (needs_human/pending).
  - Posts del blog en pending_review.
  - (informativo) auto-correcciones que el MCV APLICÓ de verdad desde el último aviso.

Silencio por defecto: el correo solo sale si hay algo NUEVO que hacer. Se calcula
una firma de lo pendiente (qué erratas, cuántos posts, qué auto-correcciones) y se
compara con la del último envío (`notification_digests`); si es la misma, no se
manda nada. Un recordatorio se repite como mucho cada DIGEST_REMINDER_DAYS días,
para que lo pendiente no se caiga del radar sin sonar todas las mañanas.

Antes de mirar la cola se intenta ARREGLAR sola cada errata abierta (el mismo
motor del botón «Arreglar»), así lo resoluble no llega nunca al correo.

Uso:
  python -m scripts.notify_review
  python -m scripts.notify_review --dry-run
  python -m scripts.notify_review --force     # manda aunque no haya novedad
  python -m scripts.notify_review --no-autofix
"""
from __future__ import annotations

import argparse
import hashlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.config import get_settings
from app.db.models import ErrataReport, NotificationDigest, Post, VerificationRecord
from app.db.session import SessionLocal
from app.services.email import send_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_SITE = "https://entreinteriores.com"
_KIND = "review"

# Cada cuánto se re-avisa de algo pendiente que no ha cambiado.
DIGEST_REMINDER_DAYS = 14


def _autofix_open_erratas(db) -> int:
    """Pasa el motor de consenso por las erratas abiertas. Devuelve cuántas cerró."""
    from app.services.errata_fix import try_fix

    open_ones = db.execute(
        select(ErrataReport).where(ErrataReport.status.in_(("needs_human", "pending")))
    ).scalars().all()
    closed = 0
    for e in open_ones:
        try:
            out = try_fix(db, e)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[autofix] errata %s falló: %s", e.id, exc)
            continue
        logger.info("[autofix] errata %s → %s (%s)", e.id, out.action, out.message)
        closed += 1 if out.closed else 0
    return closed


def _gather(db) -> dict:
    erratas = db.execute(
        select(ErrataReport)
        .where(ErrataReport.status.in_(("needs_human", "pending")))
        .order_by(ErrataReport.created_at.desc())
    ).scalars().all()
    posts_pending = db.execute(
        select(func.count()).select_from(Post).where(Post.status == "pending_review")
    ).scalar_one()
    # Auto-correcciones REALES desde el último aviso: `applied_at`, no `checked_at`
    # (que se re-sella cada noche aunque el veredicto sea el mismo de siempre).
    # Con suelo de 7 días: si hace mucho que no se manda nada, no arrastramos
    # correcciones viejas al correo como si acabaran de pasar.
    now = datetime.now(timezone.utc)
    floor = now - timedelta(days=7)
    last_sent = _last_sent_at(db)
    since = max(last_sent, floor) if last_sent else (now - timedelta(hours=24))
    autofixes = db.execute(
        select(VerificationRecord)
        .where(
            VerificationRecord.auto_applied.is_(True),
            VerificationRecord.applied_at.is_not(None),
            VerificationRecord.applied_at >= since,
        )
        .order_by(VerificationRecord.applied_at.desc())
    ).scalars().all()
    # Marca de agua: la aplicación más reciente que existe, mirada sin ventana. La
    # firma se apoya en ella porque es MONÓTONA: si no se aplica nada nuevo no se
    # mueve, mientras que "los autofixes de las últimas N horas" cambia solo con
    # que pase el tiempo, y eso hacía sonar el correo sin novedad ninguna.
    watermark = db.execute(
        select(func.max(VerificationRecord.applied_at))
        .where(VerificationRecord.auto_applied.is_(True))
    ).scalar_one()
    return {
        "erratas": erratas,
        "posts_pending": int(posts_pending),
        "autofixes": autofixes,
        "watermark": watermark,
    }


def _last_sent_at(db) -> datetime | None:
    row = db.execute(
        select(NotificationDigest)
        .where(NotificationDigest.kind == _KIND)
        .order_by(NotificationDigest.sent_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    return row.sent_at if row else None


def _signature(data: dict) -> str:
    """Huella de lo pendiente. Cambia si aparece/desaparece una errata, si cambia
    el número de posts por revisar o si se aplica una auto-corrección nueva. NO
    cambia solo porque pase el tiempo: si no ha pasado nada, no hay correo."""
    wm = data.get("watermark")
    parts = [
        "e:" + ",".join(str(e.id) for e in data["erratas"]),
        f"p:{data['posts_pending']}",
        "a:" + (wm.isoformat() if wm else "-"),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:64]


def _should_send(db, data: dict, signature: str) -> tuple[bool, str]:
    """¿Hay que mandar el correo? (motivo para el log)."""
    # Lo que dispara el correo es TRABAJO PENDIENTE (erratas sin resolver, posts por
    # revisar). Las auto-correcciones son información, no una tarea: viajan dentro del
    # correo cuando lo hay, pero no lo provocan ellas solas — si el sistema se ha
    # arreglado todo él, no hay nada que pedirle al humano. Quedan en el feed de
    # auditoría del panel.
    if not (data["erratas"] or data["posts_pending"]):
        return False, "no hay nada pendiente"
    last = db.execute(
        select(NotificationDigest)
        .where(NotificationDigest.kind == _KIND)
        .order_by(NotificationDigest.sent_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if last is None:
        return True, "primer digest"
    if last.signature != signature:
        return True, "hay novedades"
    age = datetime.now(timezone.utc) - last.sent_at
    if age >= timedelta(days=DIGEST_REMINDER_DAYS):
        return True, f"recordatorio ({age.days} días sin avisar)"
    return False, "lo mismo que el último aviso"


def _build_html(data: dict) -> str:
    er = data["erratas"]
    parts = ["<h2 style='font-family:Georgia,serif'>Entre Interiores · cosas por revisar</h2>"]

    if er:
        parts.append(f"<h3>Erratas por revisar ({len(er)})</h3>")
        parts.append("<p style='color:#666;font-size:13px'>El consenso ya intentó "
                     "arreglarlas solo: esto es lo que necesita tu mano.</p><ul>")
        for e in er[:30]:
            wrong = (e.reported_wrong or "")[:120]
            right = (e.suggested_right or "")[:120]
            why = (e.resolution_note or "")[:160]
            parts.append(
                f"<li><b>{e.target_type}</b>"
                + (f" · {e.field}" if e.field else "")
                + (f"<br>mal: <i>{wrong}</i>" if wrong else "")
                + (f"<br>debería: <i>{right}</i>" if right else "")
                + (f"<br><span style='color:#888'>{why}</span>" if why else "")
                + f" <span style='color:#888'>({e.reporter or 'anónimo'})</span></li>"
            )
        parts.append("</ul>")
        parts.append(f"<p><a href='{_SITE}/biblioteca/admin/erratas'>→ Gestionar erratas</a></p>")

    if data["posts_pending"]:
        parts.append(f"<h3>Blog en revisión ({data['posts_pending']})</h3>")
        parts.append(f"<p><a href='{_SITE}/biblioteca/admin/blog'>→ Revisar el blog</a></p>")

    if data["autofixes"]:
        parts.append(f"<h3>Auto-correcciones nuevas: {len(data['autofixes'])}</h3><ul>")
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
    ap.add_argument("--force", action="store_true", help="manda aunque no haya novedades")
    ap.add_argument("--no-autofix", action="store_true",
                    help="no intenta arreglar la cola antes de mirarla")
    args = ap.parse_args()

    settings = get_settings()
    to = settings.admin_email
    if not to:
        logger.warning("Sin ADMIN_EMAIL configurado; no se envía.")
        return

    db = SessionLocal()
    try:
        if not args.no_autofix:
            closed = _autofix_open_erratas(db)
            if closed:
                logger.info("[autofix] %d errata(s) resueltas solas antes del digest", closed)

        data = _gather(db)
        signature = _signature(data)
        send, why = _should_send(db, data, signature)
        if not send and not args.force:
            logger.info("No se envía digest: %s.", why)
            return

        n_er = len(data["erratas"])
        subject = f"[Entre Interiores] {n_er} errata(s) y {data['posts_pending']} post(s) por revisar"
        html = _build_html(data)
        if args.dry_run:
            logger.info("(dry-run) enviaría a %s (%s): %s", to, why, subject)
            logger.info(html[:600])
            return

        mid = send_email(to, subject, html)
        now = datetime.now(timezone.utc)
        db.add(NotificationDigest(kind=_KIND, signature=signature, sent_at=now))
        for e in data["erratas"]:
            e.notified_at = now
        db.commit()
        logger.info("Digest enviado a %s (%s, id=%s)", to, why, mid)
    finally:
        db.close()


if __name__ == "__main__":
    main()
