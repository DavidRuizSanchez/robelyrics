"""Barrido del Motor de Consenso de Verificación (MCV).

Orquesta los tres verificadores por eje sobre las entradas pendientes de los YAML
curados (letras, autoría, catálogo) y reporta el estado de la cola de erratas.
Pensado para el cron nocturno: idempotente y apoyado en VerificationRecord para no
re-verificar lo ya resuelto.

Por defecto procesa los overrides PENDIENTES de los YAML (barato). Con --full haría
el barrido completo del catálogo (caro: cientos de llamadas web/LLM) — NO recomendado
en cron sin control de coste.

Uso:
  python -m scripts.verify.run_consensus_sweep            # dry-run de pendientes
  python -m scripts.verify.run_consensus_sweep --apply    # aplica lo que el consenso resuelva
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import func, select

from app.db.models import ErrataReport
from app.db.session import SessionLocal
from app.services import curated_overrides as co
from scripts.verify import authorship_consensus, catalog_consensus, lyrics_consensus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _sweep_lyrics(db, apply: bool) -> None:
    pend = co.pending_only(co.lyric_overrides())
    logger.info("[letras] %d override(s) pendiente(s)", len(pend))
    for ov in pend:
        song = lyrics_consensus._resolve_song(
            db, song_id=None, album_slug=ov.get("album_slug"), title=ov.get("song_title"))
        if not song:
            logger.warning("[letras] sin canción: %s", ov.get("song_title"))
            continue
        lyrics_consensus.process_song_overrides(db, song, [ov], apply=apply)


def _sweep_authorship(db, apply: bool) -> None:
    pend = co.pending_only(co.song_credits())
    logger.info("[autoría] %d crédito(s) pendiente(s)", len(pend))
    for entry in pend:
        authorship_consensus.process(db, entry, apply=apply)


def _sweep_catalog(db, apply: bool) -> None:
    pend = co.pending_only(co.canonical_tracklists())
    logger.info("[catálogo] %d entrada(s) pendiente(s)", len(pend))
    for entry in pend:
        catalog_consensus.process(db, entry, apply=apply)


def _report_erratas(db) -> None:
    counts = dict(
        db.execute(
            select(ErrataReport.status, func.count()).group_by(ErrataReport.status)
        ).all()
    )
    if counts:
        logger.info("[erratas] estado de la cola: %s", counts)
        pend = counts.get("needs_human", 0) + counts.get("pending", 0)
        if pend:
            logger.info("[erratas] %d pendiente(s) de revisión humana", pend)


def main() -> None:
    p = argparse.ArgumentParser(description="Barrido del Motor de Consenso de Verificación.")
    p.add_argument("--apply", action="store_true", help="aplica lo que el consenso resuelva")
    p.add_argument("--full", action="store_true", help="(caro) barrido completo del catálogo — no implementado en cron")
    args = p.parse_args()

    db = SessionLocal()
    try:
        logger.info("=== Barrido MCV (apply=%s) ===", args.apply)
        _sweep_lyrics(db, args.apply)
        _sweep_authorship(db, args.apply)
        _sweep_catalog(db, args.apply)
        _report_erratas(db)
        if args.full:
            logger.warning("--full aún no implementado: el barrido total del catálogo se hará "
                           "por lotes con control de coste. De momento solo pendientes de YAML.")
        logger.info("=== Barrido MCV completado ===")
    finally:
        db.close()


if __name__ == "__main__":
    main()
