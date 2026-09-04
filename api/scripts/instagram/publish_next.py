"""Publica el siguiente post pendiente de la cola de Instagram.

Cadencia "cuentagotas": el cron lo dispara cada 2h, pero solo publica si ha
pasado el intervalo mínimo desde la última publicación. El intervalo se adapta:
mientras hay atasco (cola > BACKLOG_THRESHOLD) publica cada BACKLOG_INTERVAL_H
horas para drenarlo; en régimen normal, cada STEADY_INTERVAL_H horas.

Uso:
    python -m scripts.instagram.publish_next
    python -m scripts.instagram.publish_next --dry-run   (prepara, no publica)
    python -m scripts.instagram.publish_next --force      (ignora el intervalo)
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem
from app.db.session import SessionLocal
from app.services.instagram import config, publisher

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _pending_count(db: Session) -> int:
    """Cuántos posts esperan turno, para decidir si hay atasco.

    Cuenta también los `failed` que conservan intentos: son cola igual. Mirando
    solo pending/prepared, una cola de 47 rotos reportaba CERO pendientes, así
    que el modo atasco no se activaba justo cuando más falta hacía.
    """
    return db.execute(
        select(func.count(InstagramQueueItem.id)).where(publisher._publicable())
    ).scalar_one()


def _hours_since_last_publish(db: Session) -> float | None:
    """Horas desde la última publicación, o None si nunca se publicó."""
    last = db.execute(
        select(InstagramQueueItem.published_at)
        .where(
            InstagramQueueItem.status == "published",
            InstagramQueueItem.published_at.is_not(None),
        )
        .order_by(InstagramQueueItem.published_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if last is None:
        return None
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last).total_seconds() / 3600


def _interval_hours(pending: int) -> int:
    """Intervalo mínimo según haya atasco o no."""
    if pending > config.BACKLOG_THRESHOLD:
        return config.BACKLOG_INTERVAL_H
    return config.STEADY_INTERVAL_H


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force", action="store_true",
        help="Publica aunque no haya pasado el intervalo mínimo.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        # ¿Nos está bloqueando Meta? Entonces no se toca nada: cada intento sube
        # imágenes a Cloudinary y crea containers que van a ser rechazados. Se
        # sale con 0, no con 1: es una pausa conocida, no un fallo del script.
        # Quien avisa de esto es `notify_health` (cron 09:20).
        #
        # No hace falta sondear aparte para saber si ya se levantó: la ventana
        # del cortacircuitos caduca sola y el siguiente intento real hace de
        # sondeo. Son 4 intentos al día en vez de 96, y como las URLs de
        # Cloudinary ya están persistidas, ninguno vuelve a subir nada.
        bloqueado, motivo, desde = publisher.publicacion_bloqueada(db)
        if bloqueado and not args.force:
            logger.warning(
                "Publicación bloqueada por Meta desde %s: %s. No se intenta nada.",
                desde.isoformat() if desde else "?", motivo,
            )
            return

        # Efemérides cuyo día es HOY (aniversarios, cumpleaños): se publican su
        # día exacto, al margen del cuentagotas. Si hay alguna, se publica y no
        # se gotea también en este run (un movimiento por disparo del cron).
        pinned = publisher.due_pinned(db)
        if pinned:
            n_ok = 0
            for it in pinned:
                logger.info("Efeméride de hoy: publicando item %s «%s»", it.id, it.title)
                res = publisher.publish(db, it, dry_run=args.dry_run)
                if res.status == "failed":
                    logger.error("Error: %s", res.error)
                else:
                    n_ok += 1
            # Se sale con o sin éxito: si las de hoy fallaron, gotear encima
            # solo añade un fallo más a la misma causa (y sube más material a
            # Cloudinary). Antes solo se salía con n_ok, así que cada disparo del
            # cron intentaba los vencidos Y uno del goteo.
            logger.info(
                "Efemérides de hoy: %d publicada(s) de %d.", n_ok, len(pinned)
            )
            return

        item = publisher.next_pending(db)
        if item is None:
            logger.info("No hay posts pendientes en la cola.")
            return

        # Guard de cadencia: respeta el intervalo mínimo (salvo --force).
        if not args.force and not args.dry_run:
            pending = _pending_count(db)
            interval = _interval_hours(pending)
            hrs = _hours_since_last_publish(db)
            if hrs is not None and hrs < interval:
                logger.info(
                    "Cadencia: solo %.1fh desde la última publicación "
                    "(mínimo %dh, cola=%d). No se publica todavía.",
                    hrs, interval, pending,
                )
                return
            modo = "atasco" if pending > config.BACKLOG_THRESHOLD else "régimen"
            logger.info(
                "Cadencia OK (modo %s, intervalo %dh, cola=%d).",
                modo, interval, pending,
            )

        logger.info("Publicando item %s: «%s»", item.id, item.title)
        result = publisher.publish(db, item, dry_run=args.dry_run)
        logger.info("Estado final del item %s: %s", result.id, result.status)
        if result.status == "failed":
            logger.error("Error: %s", result.error)
            sys.exit(1)


if __name__ == "__main__":
    main()
