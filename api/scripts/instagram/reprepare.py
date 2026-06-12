"""Re-prepara items de la cola de Instagram con el código de imagen/caption ACTUAL.

Los items en estado `prepared` tienen su imagen y caption "congelados" del momento
en que se prepararon. Tras un cambio de estilo (nueva identidad visual, nuevo motor
de arte IA, nueva resolución de fotos…) hay que regenerarlos para que adopten el
estilo nuevo ANTES de publicarse. Los `pending`/`proposed` no hace falta tocarlos:
se preparan on-demand (al publicar / al aprobar) y ya usarán el código nuevo.

Uso:
    python -m scripts.instagram.reprepare              # re-prepara los `prepared`
    python -m scripts.instagram.reprepare --dry-run    # solo lista, no regenera
    python -m scripts.instagram.reprepare --status prepared,pending
    python -m scripts.instagram.reprepare --limit 5    # tope (sondeos / control de coste)

OJO: regenerar usa el motor de arte IA (OpenAI gpt-image-1) y, en noticias, el
reescritor editorial → tiene coste por item. El `--limit` permite acotarlo.
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import select

from app.db.session import SessionLocal
from app.db.models import InstagramQueueItem
from app.services.instagram import publisher

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("reprepare")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--status", default="prepared",
                    help="estados a re-preparar, separados por coma (def: prepared)")
    ap.add_argument("--limit", type=int, default=None,
                    help="tope de items a procesar (control de coste)")
    ap.add_argument("--dry-run", action="store_true",
                    help="solo lista lo que se re-prepararía, sin regenerar")
    args = ap.parse_args()

    estados = [s.strip() for s in args.status.split(",") if s.strip()]
    db = SessionLocal()
    try:
        q = (
            select(InstagramQueueItem)
            .where(InstagramQueueItem.status.in_(estados))
            .order_by(InstagramQueueItem.publish_on, InstagramQueueItem.position,
                      InstagramQueueItem.id)
        )
        if args.limit:
            q = q.limit(args.limit)
        items = db.execute(q).scalars().all()

        logger.info("Re-preparar %d item(s) en estado %s%s",
                    len(items), estados, " (DRY-RUN)" if args.dry_run else "")
        ok, fail = 0, 0
        for item in items:
            etiqueta = f"#{item.id} [{item.content_type}] {(item.title or '')[:60]}"
            if args.dry_run:
                logger.info("  · %s", etiqueta)
                continue
            try:
                publisher.prepare(db, item)
                ok += 1
                logger.info("  ✅ %s", etiqueta)
            except Exception as exc:  # noqa: BLE001
                fail += 1
                db.rollback()
                logger.error("  ❌ %s → %s", etiqueta, exc)
        if not args.dry_run:
            logger.info("Hecho: %d re-preparados, %d fallidos.", ok, fail)
    finally:
        db.close()


if __name__ == "__main__":
    main()
