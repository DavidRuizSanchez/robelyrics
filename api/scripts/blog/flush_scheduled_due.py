"""Promueve posts en estado `scheduled` a `published` cuando llega su
`scheduled_for`. Cron diario.

Llama a `publishing.flush_scheduled_due` que ya hace el re-check del cap y
dispara newsletter + revalidate al publicar.

Uso:
    python -m scripts.blog.flush_scheduled_due
"""
from __future__ import annotations

import logging

from app.db.session import SessionLocal
from app.services.publishing import flush_scheduled_due

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    with SessionLocal() as db:
        result = flush_scheduled_due(db)
    logger.info("flush_scheduled_due: %s", result)


if __name__ == "__main__":
    main()
