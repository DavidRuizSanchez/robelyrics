"""Tacha las keywords de descarga de música en las propuestas por validar.

Criterio de David (26-10-2026): «descargar discografía extremoduro» y compañía
están prohibidas. Lo nuevo ya no entra (`keyword_research` las veta al montar el
pool y las ideas), pero las propuestas que ya estaban en el banco las arrastran.

No borra nada: las marca `excluded` con `excluded_reason="descarga"` y quedan
tachadas en el panel. Es idempotente. Si una propuesta se queda sin ninguna
keyword activa, no se toca su estado: se lista para que se rechace a mano.

Uso:
    python -m scripts.blog.excluir_descargas --dry-run
    python -m scripts.blog.excluir_descargas
"""
from __future__ import annotations

import argparse
import logging

from app.db.models import ContentProposal
from app.db.session import SessionLocal
from app.services.content_merge import recalcular_objetivo
from app.services.kw_normalize import es_descarga

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def tachar(proposal) -> list[str]:
    """Marca las de descarga y devuelve las que ha tachado ahora."""
    kws = [dict(k) for k in (proposal.keywords or []) if isinstance(k, dict)]
    tachadas = []
    for k in kws:
        if not k.get("excluded") and es_descarga(k.get("keyword") or ""):
            k["excluded"] = True
            k["excluded_reason"] = "descarga"
            tachadas.append(k.get("keyword"))
    if tachadas:
        proposal.keywords = kws
        recalcular_objetivo(proposal)
    return tachadas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tocadas, vacias = [], []
    with SessionLocal() as db:
        props = (db.query(ContentProposal)
                 .filter(ContentProposal.status.in_(["proposed", "approved"]))
                 .order_by(ContentProposal.id).all())
        for p in props:
            tachadas = tachar(p)
            if not tachadas:
                continue
            tocadas.append(p.id)
            activas = [k for k in p.keywords or [] if isinstance(k, dict)
                       and not k.get("excluded")]
            if not activas:
                vacias.append(p.id)
            logger.info("#%s «%s»: %s", p.id, p.title, ", ".join(tachadas))
        if args.dry_run:
            db.rollback()
        else:
            db.commit()

    logger.info("%s %d propuestas%s", "Se tacharían en" if args.dry_run else "Tachadas en",
                len(tocadas), " (dry-run: nada escrito)" if args.dry_run else "")
    if vacias:
        logger.warning("Sin ninguna keyword activa (rechazar a mano): %s", vacias)
    if tocadas and not args.dry_run:
        logger.info("Recalcular su reparto: python -m scripts.blog.placement_backfill "
                    "--all --ids %s", ",".join(map(str, tocadas)))


if __name__ == "__main__":
    main()
