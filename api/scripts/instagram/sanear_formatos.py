"""Devuelve a su sitio los posts a los que se les colgó un formato que no era suyo.

«Clip externo» y «funcionalidad de la web» no son formas de contar un tema: son
un tema. Un CLIP es un vídeo concreto de un canal concreto; un PRODUCT, una
consulta concreta a la web. Cuando se le cuelgan a una noticia o a un verso,
pasa esto:

  - el PRODUCT machacaba título y summary del tema original, así que el post
    dejaba de hablar de lo que decía y pasaba a llamarse «Pregúntale al viento»;
  - el CLIP se quedaba esperando un vídeo que ese tema nunca iba a tener, y
    `prepare` reventaba con «este post es de formato clip externo pero no tiene
    ninguno enlazado».

Esto los devuelve a IMAGE (el camino por defecto; el repartidor de formatos ya
les dará el suyo) y, cuando había un clip enlazado, le crea su publicación
propia para no perderlo.

No borra ningún post: los devuelve a `pending` para que se regenere su material.

Uso:
  python -m scripts.instagram.sanear_formatos            # informe
  python -m scripts.instagram.sanear_formatos --apply
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

from sqlalchemy import func, select

from app.db.models import InstagramQueueItem, VideoClip
from app.db.session import SessionLocal
from app.services.instagram import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Tipos que traen su propio tema. Un post de cualquier otro tipo con formato
# CLIP o PRODUCT es un formato colgado encima de un tema ajeno.
TIPOS_PROPIOS = {"clip", "product"}
FORMATOS_PROPIOS = ("CLIP", "PRODUCT")


# Formato que le toca a cada tipo con tema propio.
FORMATO_DE = {"clip": "CLIP", "product": "PRODUCT"}


def _detectar(db) -> list[InstagramQueueItem]:
    """Formato propio colgado sobre un tema ajeno."""
    return list(db.execute(
        select(InstagramQueueItem).where(
            InstagramQueueItem.media_type.in_(FORMATOS_PROPIOS),
            InstagramQueueItem.content_type.not_in(TIPOS_PROPIOS),
            InstagramQueueItem.status != "published",
        ).order_by(InstagramQueueItem.position)
    ).scalars().all())


def _detectar_sin_su_formato(db) -> list[InstagramQueueItem]:
    """El caso contrario: un tema propio al que le falta SU formato.

    Es lo que dejaba el botón «✦ enseñar la web», que creaba los posts sin
    `media_type`: se quedaban en IMAGE, `prepare` los mandaba a la rama genérica
    y salía arte IA cualquiera en vez de la pieza que enseña la funcionalidad.
    Encima sin `media_locked`, así que el repartidor podía barrerlos.
    """
    return list(db.execute(
        select(InstagramQueueItem).where(
            InstagramQueueItem.content_type.in_(TIPOS_PROPIOS),
            InstagramQueueItem.status != "published",
        ).order_by(InstagramQueueItem.position)
    ).scalars().all())


def _post_para_el_clip(db, clip: VideoClip) -> InstagramQueueItem:
    """Publicación propia para un clip que se queda huérfano."""
    tema = (clip.subtitle or clip.video_title or "").strip()
    if not tema:
        tema = f"Vídeo de {clip.channel_title}" if clip.channel_title else "Clip de vídeo"
    pos = db.execute(
        select(func.coalesce(func.max(InstagramQueueItem.position), -1))
    ).scalar() or -1
    item = InstagramQueueItem(
        day=date.today(), slot=2, position=pos + 1,
        content_type="clip",
        content_key=f"clip:{clip.video_id}:{int(clip.start_s)}-{int(clip.end_s)}",
        title=tema[:300],
        category="Cultura",
        summary=(clip.video_title or None),
        source_name=clip.channel_title,
        source_url=clip.channel_url or clip.url,
        media_type="CLIP", media_locked=True,
        status=config.estado_inicial(),
    )
    db.add(item)
    db.flush()
    return item


def _retemar_producto(db, item: InstagramQueueItem) -> str | None:
    """Le pone a un post de «la web» un TEMA de verdad.

    Los que creó el botón viejo se llaman como la sección («Pregúntale al
    viento») y su `content_key` no dice qué se pregunta. El tema es la consulta,
    así que se coge una real del corpus y se rehace clave y título.
    """
    from app.services.instagram import product_topics as pt

    ref = (item.content_key or "").removeprefix("product:").strip()
    slug, _, cid = ref.partition(":")
    if not slug or slug not in pt.FUENTES:
        return None
    if cid:
        return None                     # ya tiene consulta: nada que rehacer

    ya_usadas = {
        (k or "").removeprefix("product:").partition(":")[2]
        for (k,) in db.execute(select(InstagramQueueItem.content_key)).all()
        if (k or "").startswith("product:")
    }
    consultas = pt.consultas_para(db, slug, excluir=ya_usadas)
    if not consultas:
        return None
    consulta = consultas[0]
    item.content_key = f"product:{slug}:{pt.consulta_id(consulta)}"
    item.title = consulta[:300]
    return consulta


def sanear(db, *, aplicar: bool) -> dict:
    afectados = _detectar(db)
    resumen = {
        "revisados": len(afectados), "devueltos": 0, "clips_reubicados": 0,
        "sin_su_formato": 0, "retemados": 0,
    }

    # Temas propios a los que les falta SU formato.
    for item in _detectar_sin_su_formato(db):
        esperado = FORMATO_DE[item.content_type]
        if item.media_type == esperado and item.media_locked:
            continue
        resumen["sin_su_formato"] += 1
        logger.info("· #%s [%s] «%s» estaba en %s (debería ser %s)",
                    item.id, item.content_type, item.title[:60],
                    item.media_type, esperado)
        if not aplicar:
            continue
        nuevo_tema = _retemar_producto(db, item) if item.content_type == "product" else None
        if nuevo_tema:
            resumen["retemados"] += 1
            logger.info("  → su tema pasa a ser «%s»", nuevo_tema)
        item.media_type = esperado
        item.media_locked = True
        item.status = "pending"        # hay que rehacer el material
        item.image_path = None
        item.media.clear()

    for item in afectados:
        clip = db.execute(
            select(VideoClip).where(VideoClip.queue_item_id == item.id)
        ).scalars().first()

        logger.info(
            "· #%s [%s] «%s» tenía formato %s%s",
            item.id, item.content_type, item.title[:60], item.media_type,
            f" con el clip #{clip.id}" if clip else "",
        )

        if not aplicar:
            resumen["devueltos"] += 1
            if clip:
                resumen["clips_reubicados"] += 1
            continue

        if clip is not None:
            nuevo = _post_para_el_clip(db, clip)
            clip.queue_item_id = nuevo.id
            resumen["clips_reubicados"] += 1
            logger.info("  → el clip se muda a su propio post #%s «%s»",
                        nuevo.id, nuevo.title[:60])

        # De vuelta al camino por defecto; el repartidor le dará su formato.
        item.media_type = "IMAGE"
        item.media_locked = False
        item.status = "pending"
        item.image_path = None
        item.media.clear()
        resumen["devueltos"] += 1

    if aplicar:
        db.commit()
    return resumen


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="aplica los cambios (sin esto solo informa)")
    args = ap.parse_args()

    with SessionLocal() as db:
        r = sanear(db, aplicar=args.apply)

    total = r["revisados"] + r["sin_su_formato"]
    logger.info("\n=== %d post(s) con el formato descolocado ===", total)
    if not total:
        logger.info("  ✓ la cola está limpia: cada formato en su tema")
        return
    if r["revisados"]:
        logger.info("  · %d con formato ajeno → devueltos a su formato natural",
                    r["devueltos"])
        logger.info("  · %d clip(s) mudados a su propia publicación",
                    r["clips_reubicados"])
    if r["sin_su_formato"]:
        logger.info("  · %d de tema propio a los que les faltaba SU formato",
                    r["sin_su_formato"])
        logger.info("  · %d retemados con una consulta real", r["retemados"])
    if not args.apply:
        logger.info("\n(informe: usa --apply para aplicarlo)")


if __name__ == "__main__":
    main()
