"""Genera el lote semanal de contenido EVERGREEN de Instagram.

Mina el corpus (frases de canciones, aniversarios, anécdotas verificadas y citas
de Robe) y encola candidatos en estado `proposed`. NO genera imagen ni caption:
el admin los aprueba en /biblioteca/admin/instagram y al aprobar se preparan.

Deduplica por `content_key` contra todo lo que ya pasó por la cola, así que es
seguro relanzarlo: nunca propone dos veces el mismo verso/efeméride/cita.

Pensado para correr una vez por semana (cron). Tras correrlo, `notify_evergreen`
manda el email al admin con el resumen.

Uso:
    python -m scripts.instagram.prepare_evergreen
    python -m scripts.instagram.prepare_evergreen --dry-run   (no inserta)
    python -m scripts.instagram.prepare_evergreen --quotes 8 --anecdotes 6
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

from sqlalchemy import func, select

from app.db.models import InstagramQueueItem
from app.db.session import SessionLocal
from app.services.instagram import evergreen

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _next_position(db) -> int:
    """Siguiente `position` libre: al final de la cola (no se cuela delante de
    lo ya reordenado a mano)."""
    max_pos = db.execute(
        select(func.coalesce(func.max(InstagramQueueItem.position), -1))
    ).scalar_one()
    return int(max_pos) + 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="No inserta nada.")
    parser.add_argument("--quotes", type=int, default=None)
    parser.add_argument("--ephemerides", type=int, default=None)
    parser.add_argument("--anecdotes", type=int, default=None)
    parser.add_argument("--robe-quotes", type=int, default=None)
    args = parser.parse_args()

    mix = dict(evergreen.DEFAULT_MIX)
    if args.quotes is not None:
        mix["quote"] = args.quotes
    if args.ephemerides is not None:
        mix["ephemeris"] = args.ephemerides
    if args.anecdotes is not None:
        mix["anecdote"] = args.anecdotes
    if args.robe_quotes is not None:
        mix["robe_quote"] = args.robe_quotes

    today = date.today()
    logger.info("Evergreen Instagram · lote · %s · mix=%s", today, mix)

    with SessionLocal() as db:
        batch = evergreen.generate_batch(db, mix=mix)
        if not batch:
            logger.info("No hay candidatos nuevos (todo deduplicado).")
            return

        encolados = 0
        for cand in batch:
            logger.info(
                "  [%s] %s", cand["content_type"], cand["title"][:70]
            )
            if args.dry_run:
                continue
            item = InstagramQueueItem(
                day=today,
                slot=2,                      # evergreen detrás de blog(0)/noticias(1)
                position=_next_position(db),
                content_type=cand["content_type"],
                content_key=cand["content_key"],
                publish_on=cand.get("publish_on"),  # efeméride: fecha fija
                title=cand["title"][:300],
                category=cand.get("category"),
                summary=cand.get("summary"),
                source_name=cand.get("source_name"),
                source_url=cand.get("source_url") or None,
                # Los posts que enseñan la web traen su formato puesto: sin esto
                # se quedaban en IMAGE y `prepare` los mandaba a la rama genérica
                # (arte IA cualquiera) en vez de componer la pieza. `media_locked`
                # los protege del repartidor de formatos.
                media_type="PRODUCT" if cand["content_type"] == "product" else "IMAGE",
                media_locked=cand["content_type"] == "product",
                status="proposed",
            )
            db.add(item)
            db.commit()
            encolados += 1

        if args.dry_run:
            logger.info("[DRY-RUN] %d candidatos (no insertados).", len(batch))
        else:
            logger.info("Lote evergreen encolado: %d propuestas.", encolados)


if __name__ == "__main__":
    main()
