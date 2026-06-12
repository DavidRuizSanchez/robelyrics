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

from app.db.models import ContentProposal
from app.db.session import SessionLocal
from app.services.draft_generator import generate_proposal_draft

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    with SessionLocal() as db:
        pending = (
            db.query(ContentProposal)
            .filter(ContentProposal.status == "approved")
            .filter(ContentProposal.body_md.is_(None))
            .order_by(ContentProposal.created_at)
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


if __name__ == "__main__":
    main()
