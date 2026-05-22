"""Publica el siguiente post pendiente de la cola de Instagram.

Pensado para correr varias veces al día (cron, p.ej. 12:30 y 20:30).

Uso:
    python -m scripts.instagram.publish_next
    python -m scripts.instagram.publish_next --dry-run   (prepara, no publica)
"""
from __future__ import annotations

import argparse
import logging
import sys

from app.db.session import SessionLocal
from app.services.instagram import publisher

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as db:
        item = publisher.next_pending(db)
        if item is None:
            logger.info("No hay posts pendientes en la cola.")
            return
        logger.info("Publicando item %s: «%s»", item.id, item.title)
        result = publisher.publish(db, item, dry_run=args.dry_run)
        logger.info("Estado final del item %s: %s", result.id, result.status)
        if result.status == "failed":
            logger.error("Error: %s", result.error)
            sys.exit(1)


if __name__ == "__main__":
    main()
