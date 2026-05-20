"""Dispatcher diario de la newsletter de Entre Interiores.

Itera todos los suscriptores `confirmed`. Para cada uno, mira sus posts
pendientes (publicados con `published_at > subscriber.last_sent_at`) y le
envía un digest si hay alguno. Actualiza `last_sent_at`.

Idempotente: relanzar dos veces seguidas no duplica envíos. Es seguro
ponerlo a correr varias veces al día.

Diseñado para correr en cron diariamente:
    0 10 * * * cd /opt/robelyrics && docker compose -f docker-compose.yml \
       -f docker-compose.prod.yml exec -T api python -m scripts.blog.send_newsletter

Flags:
  --only-email a@b.com    Solo procesa ese subscriber (útil para test).
  --dry-run               No envía ni actualiza last_sent_at.
"""
from __future__ import annotations

import argparse
import logging
import sys

from app.db.models import Subscriber
from app.db.session import SessionLocal
from app.services.newsletter import (
    dispatch_to_all_confirmed,
    dispatch_to_subscriber,
    posts_pending_for_subscriber,
)

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only-email", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    with SessionLocal() as db:
        if args.only_email:
            sub = (
                db.query(Subscriber)
                .filter(Subscriber.email == args.only_email.lower())
                .first()
            )
            if not sub:
                logger.error("No existe subscriber %s", args.only_email)
                return 1
            if sub.status != "confirmed":
                logger.warning("Subscriber %s no está confirmed (status=%s)", sub.email, sub.status)
                return 0
            pending = posts_pending_for_subscriber(db, sub)
            logger.info("Pending para %s: %d", sub.email, len(pending))
            for p in pending:
                logger.info("  · %s — %s", p.kind, p.title)
            if args.dry_run:
                logger.info("dry-run: nada enviado.")
                return 0
            sent = dispatch_to_subscriber(db, sub)
            db.commit()
            logger.info("Enviado: %s", sent)
            return 0

        # Modo completo: todos los confirmed.
        confirmed = db.query(Subscriber).filter(Subscriber.status == "confirmed").count()
        logger.info("Suscriptores confirmed: %d", confirmed)
        if args.dry_run:
            for sub in db.query(Subscriber).filter(Subscriber.status == "confirmed").all():
                pending = posts_pending_for_subscriber(db, sub)
                logger.info("  · %s — pending: %d", sub.email, len(pending))
            logger.info("dry-run: nada enviado.")
            return 0

        summary = dispatch_to_all_confirmed(db)
        logger.info(
            "Total: %d · Enviados: %d · Sin pendientes: %d",
            summary["subscribers_total"], summary["sent"], summary["no_pending"],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
