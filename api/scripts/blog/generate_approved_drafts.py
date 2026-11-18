"""Red de seguridad: genera el borrador de las propuestas APROBADAS que aún no
lo tienen.

Al aprobar una propuesta desde el panel se lanza la generación del cuerpo en
segundo plano (`admin._generate_draft_bg`). Este script cubre los casos en que
eso no llegó a completarse: aprobación en bloque de muchas a la vez, reinicio
del proceso, o un fallo puntual del LLM. Idempotente: solo toca las `approved`
sin `body_md`.

Uso:
    python -m scripts.blog.generate_approved_drafts
    python -m scripts.blog.generate_approved_drafts --limit 5
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from sqlalchemy import or_, text

from app.db.models import ContentProposal
from app.db.session import SessionLocal
from app.services.draft_generator import generate_proposal_draft, juzgar_borrador

# Las programadas se preparan con este margen: la de «Destrozares» estaba programada
# desde agosto y su borrador se escribió a las 08:00 del día de publicar (18-11-2026).
MARGEN_DIAS = 14
CANDADO = 18112026  # pg_advisory_lock de este cron

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--juzgar", type=int, default=1,
                        help="borradores sin juzgar que se juzgan por pasada (cuesta LLM)")
    args = parser.parse_args()

    with SessionLocal() as db:
        # Un borrador con reescrituras tarda minutos y el cron corre cada 5: una sola
        # pasada a la vez, o dos juzgarían (y pagarían) la misma propuesta.
        if not db.execute(text("select pg_try_advisory_lock(:k)"), {"k": CANDADO}).scalar():
            logger.info("Otra pasada sigue trabajando: esta se salta.")
            return
        limite = date.today() + timedelta(days=MARGEN_DIAS)
        pending = (
            db.query(ContentProposal)
            .filter(or_(ContentProposal.status == "approved",
                        (ContentProposal.status == "scheduled")
                        & (ContentProposal.scheduled_for <= limite)))
            .filter(ContentProposal.body_md.is_(None))
            .order_by(ContentProposal.scheduled_for.nulls_last(), ContentProposal.created_at)
            .limit(args.limit)
            .all()
        )
        logger.info("Aprobadas sin borrador: %d", len(pending))
        done = 0
        for p in pending:
            logger.info("[%s] %s", p.kind, p.title)
            try:
                if generate_proposal_draft(db, p):
                    done += 1
            except Exception:  # noqa: BLE001
                logger.exception("falló el borrador de la propuesta %s", p.id)
        logger.info("Borradores generados: %d/%d", done, len(pending))

        # Borradores que nunca pasaron por el juicio (los de antes del 18-11-2026): se
        # juzgan poco a poco, los programados más cercanos primero.
        sin_juzgar = (
            db.query(ContentProposal)
            .filter(ContentProposal.status.in_(("approved", "scheduled")))
            .filter(ContentProposal.kind != "news")
            .filter(ContentProposal.body_md.isnot(None))
            .filter(ContentProposal.review_verdict.is_(None))
            .order_by(ContentProposal.scheduled_for.nulls_last(), ContentProposal.created_at)
            .limit(args.juzgar)
            .all()
        )
        for p in sin_juzgar:
            try:
                # Solo se JUZGA (sin reescribir): el backlog de antes del 18-11-2026 se
                # revisa con David antes de regenerar nada (asesor: reescribiría títulos
                # y cuerpos de 39 aprobadas sin que nadie las hubiera visto).
                juzgar_borrador(db, p, reescribir=False)
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
                logger.exception("falló el juicio de la propuesta %s", p.id)
        if sin_juzgar:
            logger.info("Juzgadas: %d", len(sin_juzgar))


if __name__ == "__main__":
    main()
