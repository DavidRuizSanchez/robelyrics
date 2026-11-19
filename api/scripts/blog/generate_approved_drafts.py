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

from sqlalchemy import or_, text

from app.db.models import ContentProposal
from app.db.session import SessionLocal
from app.services.draft_generator import generate_proposal_draft, juzgar_borrador

CANDADO = 18112026  # pg_advisory_lock de este cron

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


MAX_FALLOS_SIN_CUERPO = 2


def anotar_fallo(p: ContentProposal) -> None:
    """Un borrador que no sale (sin historias bastantes, sin material) se reintentaba
    cada 5 minutos, con su gasto en OpenAI: la #399 cuatro veces seguidas y la #556 sin
    parar (19-11-2026). Al segundo fallo queda retenida por falta de material."""
    from app.services.draft_generator import con_nota

    previas = p.review_reasons if isinstance(p.review_reasons, dict) else {}
    fallos = int(previas.get("fallos_borrador") or 0) + 1
    if fallos >= MAX_FALLOS_SIN_CUERPO:
        p.review_verdict = "retenida"
        p.review_reasons = con_nota({
            "pasa": False, "bloquea": "material", "fallos_borrador": fallos,
            "motivos": [f"No sale un borrador con el material que hay ({fallos} intentos). "
                        "«Reescribir» en el panel lo vuelve a intentar."],
            "faltan_datos": []}, previas)
    else:
        p.review_reasons = {**previas, "fallos_borrador": fallos}
    logger.info("borrador sin cuerpo para la propuesta %s (%d fallo/s)", p.id, fallos)


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
        # Toda programada sin borrador se escribe ya, sea cual sea su fecha: tras
        # «Reescribir» en el panel, una efeméride del 10-12 no puede esperar a estar a
        # 14 días (18-11-2026). Escribir antes no cuesta más y da margen para revisar.
        pending = (
            db.query(ContentProposal)
            .filter(or_(ContentProposal.status == "approved",
                        ContentProposal.status == "scheduled"))
            .filter(ContentProposal.body_md.is_(None))
            # Retenida sin cuerpo = el redactor ya lo intentó y no hay material: no se
            # insiste cada 5 minutos («Reescribir» en el panel limpia el veredicto).
            .filter(or_(ContentProposal.review_verdict.is_(None),
                        ContentProposal.review_verdict != "retenida"))
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
                else:
                    anotar_fallo(p)
                    db.commit()
            except Exception:  # noqa: BLE001
                logger.exception("falló el borrador de la propuesta %s", p.id)
                db.rollback()
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
