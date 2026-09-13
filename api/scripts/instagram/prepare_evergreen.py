"""Genera el lote semanal de contenido EVERGREEN de Instagram.

Mina el corpus (frases de canciones, aniversarios, anécdotas verificadas y citas
de Robe) y encola candidatos en estado `proposed`. NO genera imagen ni caption:
el admin los aprueba en /biblioteca/admin/instagram y al aprobar se preparan.

Deduplica por `content_key` contra todo lo que ya pasó por la cola, así que es
seguro relanzarlo: nunca propone dos veces el mismo verso/efeméride/cita.

Pensado para correr una vez por semana (cron). Tras correrlo, `notify_evergreen`
manda el email al admin con el resumen.

NO repone por encima del atasco: si la cola de goteo ya llega a
`BACKLOG_THRESHOLD`, el mix se recorta al hueco que quede (y a cero si no queda
ninguno). El evergreen no caduca —lo que no entre hoy entra la semana que viene
y `content_key` evita repetirlo—, así que seguir generando con la cola llena
solo entierra lo que ya espera turno. `--sin-limite` se lo salta.

Uso:
    python -m scripts.instagram.prepare_evergreen
    python -m scripts.instagram.prepare_evergreen --dry-run   (no inserta)
    python -m scripts.instagram.prepare_evergreen --quotes 8 --anecdotes 6
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

from sqlalchemy import func, or_, select

from app.db.models import InstagramQueueItem
from app.db.session import SessionLocal
from app.services.instagram import config, evergreen, publisher

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _next_position(db) -> int:
    """Siguiente `position` libre: al final de la cola (no se cuela delante de
    lo ya reordenado a mano)."""
    max_pos = db.execute(
        select(func.coalesce(func.max(InstagramQueueItem.position), -1))
    ).scalar_one()
    return int(max_pos) + 1


# Las efemérides no compiten por el goteo: llevan `publish_on` y salen a su
# fecha por `due_pinned`. Recortarlas por atasco sería perder el aniversario,
# que no se puede publicar otro día.
TIPOS_CON_FECHA_FIJA = ("ephemeris",)


def _hueco_de_goteo(db) -> int:
    """Cuántas propuestas de goteo caben sin empeorar el atasco.

    Medido el 13-sep-2026: entraban 20-23 items por semana y salían 15, así que
    la cola no bajaba NUNCA de `BACKLOG_THRESHOLD` y los 16 posts condenados en
    agosto no iban a volver jamás — `recover_failed` decía literalmente "caben 0".
    El déficit era el evergreen, que es justo lo que NO caduca: lo que no se
    proponga hoy se propone la semana que viene y `content_key` lo deduplica.

    Es un HUECO, no un tope: vale `umbral − lo que ya hay`. Devolver el umbral a
    secas volvería a meter 15 sobre los que ya estaban.
    """
    en_cola = db.execute(
        select(func.count(InstagramQueueItem.id)).where(
            or_(publisher._publicable(), InstagramQueueItem.status == "proposed"),
            InstagramQueueItem.publish_on.is_(None),
            InstagramQueueItem.publish_at.is_(None),
        )
    ).scalar_one()
    return max(0, config.BACKLOG_THRESHOLD - int(en_cola))


def recortar_al_hueco(mix: dict, hueco: int) -> dict:
    """Reparte el hueco entre los tipos que gotean, en round-robin.

    Round-robin y no proporcional para que un lote corto no salga entero de un
    solo tipo: con hueco 2 se prefiere un verso y una anécdota a dos versos.
    """
    recortado = {
        t: n for t, n in mix.items() if t in TIPOS_CON_FECHA_FIJA
    }
    gotean = {t: n for t, n in mix.items() if t not in TIPOS_CON_FECHA_FIJA}
    if sum(gotean.values()) <= hueco:
        return dict(mix)

    recortado.update({t: 0 for t in gotean})
    quedan = hueco
    while quedan > 0:
        movido = False
        for tipo, tope in gotean.items():
            if quedan > 0 and recortado[tipo] < tope:
                recortado[tipo] += 1
                quedan -= 1
                movido = True
        if not movido:
            break
    return recortado


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="No inserta nada.")
    parser.add_argument("--quotes", type=int, default=None)
    parser.add_argument("--ephemerides", type=int, default=None)
    parser.add_argument("--anecdotes", type=int, default=None)
    parser.add_argument("--robe-quotes", type=int, default=None)
    parser.add_argument(
        "--sin-limite", action="store_true",
        help="Genera el mix entero aunque la cola esté atascada.",
    )
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

    with SessionLocal() as db:
        if not args.sin_limite:
            hueco = _hueco_de_goteo(db)
            pedido = dict(mix)
            mix = recortar_al_hueco(mix, hueco)
            if mix != pedido:
                logger.info(
                    "Atasco: caben %d propuestas de goteo (umbral %d). "
                    "Mix recortado de %s a %s.",
                    hueco, config.BACKLOG_THRESHOLD, pedido, mix,
                )
        logger.info("Evergreen Instagram · lote · %s · mix=%s", today, mix)
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
