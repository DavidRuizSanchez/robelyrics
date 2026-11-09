"""Publica el siguiente post pendiente de la cola de Instagram.

Cadencia "cuentagotas": el cron lo dispara cada 15 min, pero solo publica dentro
de las franjas fijas (`IG_SLOTS`, 13:30 y 20:30) y una vez por franja. El vídeo va aparte: un
carril propio de `VIDEO_PER_DAY` al día por la tarde, encima del goteo.
(Hasta el 09-11-2026 mandaba un intervalo de 12 h —10 h con atasco— desde el
último post, y la hora caía donde cayera.)

Uso:
    python -m scripts.instagram.publish_next
    python -m scripts.instagram.publish_next --dry-run   (prepara, no publica)
    python -m scripts.instagram.publish_next --force      (ignora el intervalo)
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem
from app.db.session import SessionLocal
from app.services.instagram import config, publisher, scheduling

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _pending_count(db: Session) -> int:
    """Cuántos posts esperan turno, para decidir si hay atasco.

    Cuenta también los `failed` que conservan intentos: son cola igual. Mirando
    solo pending/prepared, una cola de 47 rotos reportaba CERO pendientes, así
    que el modo atasco no se activaba justo cuando más falta hacía.
    """
    return db.execute(
        select(func.count(InstagramQueueItem.id)).where(
            publisher._publicable(), *publisher._filtro_video(False))
    ).scalar_one()


def _hours_since_last_publish(db: Session) -> float | None:
    """Horas desde la última publicación del GOTEO, o None si nunca se publicó.

    El vídeo va por su carril y no cuenta: si contara, cada reel retrasaría el
    siguiente carrusel 12 h y el total no subiría, solo cambiaría de formato."""
    last = db.execute(
        select(InstagramQueueItem.published_at)
        .where(
            InstagramQueueItem.status == "published",
            InstagramQueueItem.published_at.is_not(None),
            *publisher._filtro_video(False),
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


_TZ = ZoneInfo("Europe/Madrid")

# Horas que dura una franja abierta: si el cron estuvo caído a las 13:30, el post
# sale en la pasada siguiente, pero no a las 19:00 pisando la franja de la noche.
VENTANA_FRANJA_H = 3


def _turno_del_goteo(db: Session, ahora: datetime | None = None) -> tuple[bool, str]:
    """¿Toca publicar del goteo? Solo dentro de una franja (`IG_SLOTS`, 13:30 y
    20:30 por defecto) y si en ella no ha salido aún nada del goteo.

    Antes mandaba un intervalo de 12 h desde el último post, así que la hora la
    decidía la primera publicación de la cadena: el feed acababa con posts a las
    01:45. Medido el 09-11-2026 sobre 211 posts, ninguna franja rinde más que
    otra, así que se fijan dos para que el ritmo sea regular y nada salga de
    madrugada. Una efeméride o un post fijado que sale en la franja la ocupa.
    """
    ahora = ahora or datetime.now(timezone.utc)
    local = ahora.astimezone(_TZ)
    abierta = None
    for franja in sorted(scheduling.slots_diarios()):
        inicio = datetime.combine(local.date(), franja, tzinfo=_TZ)
        if inicio <= local < inicio + timedelta(hours=VENTANA_FRANJA_H):
            abierta = inicio
    if abierta is None:
        return False, f"fuera de franja ({local:%H:%M} Madrid)"
    ya = db.execute(
        select(func.count(InstagramQueueItem.id)).where(
            InstagramQueueItem.status == "published",
            InstagramQueueItem.published_at >= abierta.astimezone(timezone.utc),
            *publisher._filtro_video(False),
        )
    ).scalar_one()
    if ya:
        return False, f"la franja de las {abierta:%H:%M} ya tiene post"
    return True, f"franja de las {abierta:%H:%M}"


def _toca_video(db: Session, ahora: datetime | None = None) -> tuple[bool, str]:
    """¿Sale ya el vídeo del día? Dentro de la franja de tarde (hora de Madrid) y
    solo si hoy no ha salido ya `VIDEO_PER_DAY`. Cuenta cualquier vídeo, también
    un reel de efeméride fijado, para no meter dos el mismo día."""
    ahora = ahora or datetime.now(timezone.utc)
    local = ahora.astimezone(_TZ)
    if not (config.VIDEO_DESDE_HORA <= local.hour < config.VIDEO_HASTA_HORA):
        return False, f"fuera de franja ({local:%H:%M} Madrid)"
    inicio = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    hoy = db.execute(
        select(func.count(InstagramQueueItem.id)).where(
            InstagramQueueItem.status == "published",
            InstagramQueueItem.published_at >= inicio,
            *publisher._filtro_video(True),
        )
    ).scalar_one()
    if hoy >= config.VIDEO_PER_DAY:
        return False, f"hoy ya salieron {hoy} vídeo(s)"
    return True, ""


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

        # Carril de vídeo: 1 al día por la tarde, ENCIMA del goteo. Un
        # movimiento por disparo del cron: si sale el vídeo, el goteo espera a
        # la pasada siguiente (15 min).
        video = publisher.next_pending(db, video=True)
        if video is not None:
            toca, motivo = _toca_video(db)
            if toca:
                logger.info("Vídeo del día: publicando item %s «%s»", video.id, video.title)
                res = publisher.publish(db, video, dry_run=args.dry_run)
                logger.info("Estado final del item %s: %s", res.id, res.status)
                if res.status == "failed":
                    logger.error("Error: %s", res.error)
                    sys.exit(1)
                return
            logger.info("Vídeo %s en espera: %s.", video.id, motivo)

        item = publisher.next_pending(db, video=False)
        if item is None:
            logger.info("No hay posts pendientes en la cola.")
            return

        # Guard de franja: el goteo sale a las horas fijas (salvo --force).
        if not args.force and not args.dry_run:
            toca, motivo = _turno_del_goteo(db)
            if not toca:
                logger.info("Goteo en espera: %s.", motivo)
                return
            logger.info("Goteo: %s (cola=%d).", motivo, _pending_count(db))

        logger.info("Publicando item %s: «%s»", item.id, item.title)
        result = publisher.publish(db, item, dry_run=args.dry_run)
        logger.info("Estado final del item %s: %s", result.id, result.status)
        if result.status == "failed":
            logger.error("Error: %s", result.error)
            sys.exit(1)


if __name__ == "__main__":
    main()
