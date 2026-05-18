"""One-shot: invita a la newsletter a todos los usuarios YA registrados
(con email verificado) que no estén ya suscritos.

Por usuario:
  - Si ya existe Subscriber `confirmed`         → SKIP (ya suscrito).
  - Si ya existe Subscriber `unsubscribed`      → SKIP (respetamos baja).
  - Si ya existe Subscriber `pending`           → reenvía email de invite
                                                  con token nuevo.
  - Si NO existe Subscriber                     → crea pending + envía
                                                  email de invitación.

Idempotente: relanzar no duplica y respeta a quien ya rechazó.

Por defecto es **dry-run**: lista a quién enviaría sin enviar.
Para ejecutar real, pasar `--apply`.

Uso:
    docker compose exec api python -m scripts.blog.invite_users_to_newsletter
    docker compose exec api python -m scripts.blog.invite_users_to_newsletter --apply
    docker compose exec api python -m scripts.blog.invite_users_to_newsletter --apply --only-email a@b.com
"""
from __future__ import annotations

import argparse
import logging
import os
import secrets
import sys

from sqlalchemy import select

from app.db.models import Subscriber, User
from app.db.session import SessionLocal
from app.services.email import EmailError, render_newsletter_invite_email, send_email

logger = logging.getLogger(__name__)


def site_url() -> str:
    return os.environ.get("SITE_URL", "https://entreinteriores.com").rstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Ejecuta real. Sin esto, solo lista lo que se enviaría.",
    )
    parser.add_argument(
        "--only-email",
        default=None,
        help="Limita la invitación a un único email. Útil para probar primero.",
    )
    parser.add_argument(
        "--include-unverified",
        action="store_true",
        help="Por defecto solo se invita a usuarios con email_verified_at. "
        "Con esta flag se incluye a los no verificados (no recomendado).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    base_url = site_url()
    only_email = args.only_email.lower() if args.only_email else None

    with SessionLocal() as db:
        user_q = db.query(User)
        if not args.include_unverified:
            user_q = user_q.filter(User.email_verified_at.isnot(None))
        if only_email:
            user_q = user_q.filter(User.email == only_email)
        users = list(user_q.all())

        logger.info("Usuarios candidatos: %d", len(users))

        to_create = 0
        to_resend = 0
        already_confirmed = 0
        already_unsubscribed = 0

        plan: list[tuple[User, Subscriber | None, str]] = []

        for u in users:
            email = u.email.lower()
            sub = db.execute(
                select(Subscriber).where(Subscriber.email == email)
            ).scalar_one_or_none()

            if sub is None:
                plan.append((u, None, "create_and_invite"))
                to_create += 1
            elif sub.status == "confirmed":
                plan.append((u, sub, "skip_confirmed"))
                already_confirmed += 1
            elif sub.status == "unsubscribed":
                plan.append((u, sub, "skip_unsubscribed"))
                already_unsubscribed += 1
            elif sub.status == "pending":
                plan.append((u, sub, "resend_invite"))
                to_resend += 1
            elif sub.status == "bounced":
                plan.append((u, sub, "skip_bounced"))
            else:
                plan.append((u, sub, f"skip_unknown_status:{sub.status}"))

        logger.info("Resumen:")
        logger.info("  Crear + invitar:        %d", to_create)
        logger.info("  Reenviar (pending):     %d", to_resend)
        logger.info("  Skip (ya confirmado):   %d", already_confirmed)
        logger.info("  Skip (ya dado de baja): %d", already_unsubscribed)

        for u, _sub, action in plan:
            logger.info("  · %-45s → %s", u.email, action)

        if not args.apply:
            logger.info("\ndry-run: nada enviado. Lanza con --apply para ejecutar.")
            return 0

        sent_ok = 0
        sent_failed = 0

        for u, sub, action in plan:
            if action not in ("create_and_invite", "resend_invite"):
                continue

            email = u.email.lower()
            if sub is None:
                sub = Subscriber(
                    email=email,
                    status="pending",
                    confirm_token=secrets.token_urlsafe(32),
                    unsubscribe_token=secrets.token_urlsafe(32),
                    source="invite_existing_users",
                )
                db.add(sub)
                db.flush()
            elif action == "resend_invite":
                sub.confirm_token = secrets.token_urlsafe(32)
                db.flush()

            confirm_url = f"{base_url}/newsletter/confirmar?token={sub.confirm_token}"
            html, text = render_newsletter_invite_email(confirm_url)
            try:
                send_email(
                    to=email,
                    subject="Hemos abierto un diario · Entre Interiores",
                    html=html,
                    text=text,
                )
                sent_ok += 1
            except EmailError as e:
                logger.warning("Send failed for %s: %s", email, e)
                sent_failed += 1

        db.commit()

        logger.info("\nEnvíos OK: %d · fallidos: %d", sent_ok, sent_failed)
        return 0 if sent_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
