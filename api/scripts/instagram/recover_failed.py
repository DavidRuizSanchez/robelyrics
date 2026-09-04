"""Devuelve a la cola lo que un bloqueo de Meta condenó, y descarta lo caducado.

Cuando Meta bloquea la publicación, los posts fallan por algo que no es suyo. El
código ya no les quema intentos por eso (`errors.quema_intento`), pero los que se
quedaron sin intentos ANTES de ese arreglo siguen fuera de la cola: `_publicable`
los excluye y nadie los vuelve a mirar. Esto los repesca.

No todo se repesca. Una noticia de hace tres semanas ya no es una noticia y
publicarla ahora sería mentir por omisión de fecha; una efeméride cuyo día pasó,
igual. Eso se descarta con su motivo escrito. Lo evergreen —versos, anécdotas,
citas, producto— no caduca y vuelve entero.

Lo que NO hace: tocar Cloudinary. Las piezas ya subidas conservan su `url`, así
que `publish` las salta y la repesca no cuesta ni un céntimo.

Uso:
  python -m scripts.instagram.recover_failed --dry-run
  python -m scripts.instagram.recover_failed --apply
  python -m scripts.instagram.recover_failed --apply --limit 4
  python -m scripts.instagram.recover_failed --apply --solo-descartar
"""
from __future__ import annotations

import argparse
import logging
from datetime import UTC, date, datetime

from sqlalchemy import func, select

from app.db.models import InstagramQueueItem
from app.db.session import SessionLocal
from app.services.instagram import config, publisher

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Contenido atado a un momento: si ese momento pasó, ya no se publica.
TIPOS_DE_ACTUALIDAD = ("news", "blog")


def caduco(item: InstagramQueueItem, hoy: date) -> bool:
    """¿Este post ha perdido el tren?"""
    if item.content_type in TIPOS_DE_ACTUALIDAD:
        return True
    if item.content_type == "ephemeris":
        # Una efeméride es evergreen como TEMA pero no como FECHA: la del 3 de
        # agosto no se publica en septiembre, se vuelve a proponer el año que viene.
        cuando = item.publish_on or item.day
        return bool(cuando and cuando < hoy)
    return False


def _condenados(db) -> list[InstagramQueueItem]:
    return db.execute(
        select(InstagramQueueItem)
        .where(
            InstagramQueueItem.status == "failed",
            InstagramQueueItem.attempts >= config.MAX_PUBLISH_ATTEMPTS,
        )
        .order_by(InstagramQueueItem.day, InstagramQueueItem.slot, InstagramQueueItem.id)
    ).scalars().all()


def _repescar(db, item: InstagramQueueItem, cola_al_final: int) -> str:
    item.attempts = 0
    item.error = None
    item.error_code = None
    item.last_attempt_at = None
    # Limpiar el momento fijado NO es cosmético: `due_pinned` publica de golpe
    # TODO lo vencido en la misma pasada del cron, sin pasar por el cuentagotas.
    # Con las fechas viejas puestas, repescar 24 posts los volcaría todos al feed
    # de una vez, justo después de que Meta levante una restricción.
    item.publish_at = None
    if item.publish_on and item.publish_on < date.today():
        item.publish_on = None
    item.position = cola_al_final
    item.status = "prepared" if publisher._media_lista(item) else "pending"
    return item.status


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="escribe de verdad")
    ap.add_argument("--dry-run", action="store_true", help="solo enseña qué haría")
    ap.add_argument(
        "--limit", type=int, default=config.BACKLOG_THRESHOLD,
        help=(
            "cuántos evergreen devolver a la cola en esta pasada. Por encima de "
            f"{config.BACKLOG_THRESHOLD} se activa el modo atasco "
            f"({config.BACKLOG_INTERVAL_H} h entre posts) y el ritmo se dispara; "
            "el script es idempotente, así que se repite cuando la cola baje."
        ),
    )
    ap.add_argument("--solo-descartar", action="store_true",
                    help="descarta lo caducado y no repesca nada")
    ap.add_argument("--todos", action="store_true",
                    help="ignora --limit y repesca todo lo recuperable de golpe")
    args = ap.parse_args()

    if not args.apply and not args.dry_run:
        ap.error("hay que elegir: --dry-run o --apply")

    hoy = date.today()
    db = SessionLocal()
    try:
        items = _condenados(db)
        if not items:
            logger.info("No hay ningún post sin intentos. Nada que hacer.")
            return

        caducados = [i for i in items if caduco(i, hoy)]
        recuperables = [i for i in items if not caduco(i, hoy)]
        logger.info(
            "%d post(s) sin intentos: %d caducados, %d recuperables.",
            len(items), len(caducados), len(recuperables),
        )

        for it in caducados:
            logger.info(
                "  DESCARTAR  #%s [%s · %s] %s",
                it.id, it.content_type, it.day, (it.title or "")[:60],
            )
        a_repescar = recuperables if (args.todos or args.solo_descartar) else \
            recuperables[: max(0, args.limit)]
        if args.solo_descartar:
            a_repescar = []
        for it in a_repescar:
            logger.info(
                "  REPESCAR   #%s [%s · %s] %s",
                it.id, it.content_type, it.day, (it.title or "")[:60],
            )
        pendientes = len(recuperables) - len(a_repescar)
        if pendientes > 0:
            logger.info(
                "  (%d recuperable(s) se quedan para otra pasada: --limit %d)",
                pendientes, args.limit,
            )

        if not args.apply:
            logger.info("(dry-run) no se ha escrito nada.")
            return

        cola = db.execute(
            select(func.coalesce(func.max(InstagramQueueItem.position), 0))
        ).scalar_one()
        ahora = datetime.now(UTC).strftime("%d-%m-%Y")
        for it in caducados:
            it.status = "discarded"
            it.error = (
                f"descartado el {ahora}: caducó mientras la publicación estaba "
                f"bloqueada. Motivo original: {(it.error or 'sin detalle')[:400]}"
            )
        for n, it in enumerate(a_repescar, start=1):
            estado = _repescar(db, it, cola + n)
            logger.info("  #%s → %s", it.id, estado)
        db.commit()
        logger.info(
            "Hecho: %d descartado(s), %d de vuelta en la cola.",
            len(caducados), len(a_repescar),
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
