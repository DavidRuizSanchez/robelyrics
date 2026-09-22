"""Barrido de identidad sobre los posts de noticias YA encolados o publicados.

Busca en lo viejo el patrón que destapó el item 348: una entidad mal
identificada, una afirmación que el artículo no sostiene, o una foto cuya
procedencia no acredita a quién retrata.

NADA SE BORRA NI SE DESPUBLICA. Se marca y decide una persona — misma política
que `scripts/seo/audit_images.py`, y por el mismo motivo: los metadatos son
irregulares y un falso positivo se llevaría por delante contenido bueno de una
cuenta pública. Además, aquí no hay camino de despublicación en el código: para
retirar un post hay que entrar en instagram.com. El script lo dice en su salida
en vez de dar a entender que lo arregla.

NO va al crontab, misma decisión que `scripts/blog/audit_published.py`, hasta
haberlo calibrado sobre la cola real.

Dos límites que conviene saber antes de leer la salida:

  · Las fotos publicadas están re-alojadas en Cloudinary, así que perdieron su
    fichero de Commons: `verify_provenance` dirá `unverifiable` de casi todas.
    Eso NO es un hallazgo, es el estado normal de lo ya publicado.
  · `news_items` se purga a los 7 días, así que de una noticia vieja solo queda
    el snapshot de la cola. El artículo se vuelve a descargar de `source_url`
    cuando responde; si no, el análisis se queda en el titular y se dice.

Uso:
    python -m scripts.instagram.audit_identidad                  (dry-run)
    python -m scripts.instagram.audit_identidad --limit 50
    python -m scripts.instagram.audit_identidad --mark           (marca needs_human)
    python -m scripts.instagram.audit_identidad --csv /tmp/x.csv
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys

from sqlalchemy import select

from app.db.models import InstagramQueueItem
from app.db.session import SessionLocal
from app.services import news_entities as ne
from app.services.article_extract import fetch_article
from app.services.image_guard import _norm

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Clases de hallazgo.
ENTIDAD_AMBIGUA = "entidad_ambigua"
CONTRADICE_IDENTIDAD = "contradice_identidad"
SIN_MATERIAL = "sin_material"


def _hallazgos(db, item: InstagramQueueItem) -> list[dict]:
    """Qué le pasa a este post. Lista vacía = nada que mirar."""
    from app.services.instagram.caption_guard import contradice_la_identidad

    caption = item.caption or ""
    fuente = item.source_url or ""
    material = ""
    if fuente:
        res = fetch_article(fuente, timeout=12)
        material = res.text or ""

    if not material:
        # Sin artículo no se puede juzgar el contenido, pero SÍ se puede decir
        # que aquel post se escribió sin nada debajo, que es el origen de todo.
        return [{
            "clase": SIN_MATERIAL,
            "detalle": "No se ha podido recuperar el artículo: el post se juzgó solo por el titular.",
        }]

    entidades = ne.resolve_all(db, material, item.title or "")
    fuera: list[dict] = []

    for e in entidades:
        if e.silenciada and _norm(e.mention.surface) in _norm(caption):
            fuera.append({
                "clase": ENTIDAD_AMBIGUA,
                "detalle": f"El caption nombra a «{e.mention.surface}» y no se puede "
                           f"identificar: {e.reason}",
            })

    for problema in contradice_la_identidad(caption, entidades):
        fuera.append({"clase": CONTRADICE_IDENTIDAD, "detalle": problema})

    return fuera


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=40,
                        help="Cuántos posts mirar (los más recientes).")
    parser.add_argument("--mark", action="store_true",
                        help="Marca `needs_human` en los que tengan hallazgos.")
    parser.add_argument("--csv", help="Vuelca los hallazgos a un CSV.")
    parser.add_argument("--solo-publicados", action="store_true",
                        help="Limita a los que salieron de verdad.")
    args = parser.parse_args()

    from app.services.instagram import graph_api

    with SessionLocal() as db:
        q = select(InstagramQueueItem).where(
            InstagramQueueItem.content_type == "news",
            InstagramQueueItem.caption.is_not(None),
        )
        if args.solo_publicados:
            q = q.where(InstagramQueueItem.ig_media_id.is_not(None))
        items = db.execute(
            q.order_by(InstagramQueueItem.id.desc()).limit(args.limit)
        ).scalars().all()

        logger.info("Revisando %d posts de noticias…", len(items))
        filas: list[dict] = []
        for item in items:
            try:
                hallazgos = _hallazgos(db, item)
            except Exception as exc:  # noqa: BLE001
                logger.warning("  item %s: no se pudo revisar (%s)", item.id, exc)
                continue
            if not hallazgos:
                continue
            publicado = bool(item.ig_media_id)
            enlace = graph_api.permalink(item.ig_media_id) if publicado else ""
            for h in hallazgos:
                filas.append({
                    "id": item.id,
                    "dia": item.day.isoformat() if item.day else "",
                    "publicado": "sí" if publicado else "no",
                    "titulo": (item.title or "")[:90],
                    "clase": h["clase"],
                    "detalle": h["detalle"][:300],
                    "enlace": enlace or "",
                })
            logger.info(
                "  · %s#%d %s — %s",
                "PUBLICADO " if publicado else "en cola  ", item.id,
                (item.title or "")[:55], hallazgos[0]["clase"],
            )
            if args.mark:
                item.needs_human = True
                db.commit()

    if not filas:
        logger.info("Nada que revisar.")
        return 0

    por_clase: dict[str, int] = {}
    for f in filas:
        por_clase[f["clase"]] = por_clase.get(f["clase"], 0) + 1
    logger.info("Hallazgos: %s", " · ".join(f"{k}={v}" for k, v in sorted(por_clase.items())))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()))
            w.writeheader()
            w.writerows(filas)
        logger.info("CSV en %s", args.csv)

    publicados = [f for f in filas if f["publicado"] == "sí"]
    if publicados:
        logger.warning(
            "%d hallazgos están en posts YA PUBLICADOS. Retirarlos es manual, "
            "desde instagram.com: aquí no hay despublicación y no conviene que la "
            "haya. Enlaces arriba.",
            len(publicados),
        )
    if not args.mark:
        logger.info("(dry-run: no se ha marcado nada. Usa --mark para que salgan en el panel.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
