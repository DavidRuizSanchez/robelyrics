"""Backfill de MEDIOS (vídeo + foto) en propuestas aprobadas/programadas.

Para cada propuesta `approved`/`scheduled` (las que se van a publicar):
  - normaliza enlaces markdown de YouTube → URL desnuda (se embeben como reproductor),
  - si no tiene vídeo, busca uno claramente del tema (find_video) y lo embebe + set `video`,
  - si no tiene foto (hero), intenta una de sus entidades o de la web.

Best-effort: si no hay medios del tema, se queda como está (no inventa nada).

Uso:
    python -m scripts.blog.enrich_media --dry-run
    python -m scripts.blog.enrich_media
    python -m scripts.blog.enrich_media --ids 183 197
"""
from __future__ import annotations

import argparse
import logging

from app.db.models import ContentProposal
from app.db.session import SessionLocal
from app.services.text_sanitizer import embed_youtube_links

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Por defecto solo lo que va a publicarse pronto (aprobado/programado). Para el
# banco entero ('proposed') hay que pasar --ids explícitos.
LIVE = ("approved", "scheduled")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ids", type=int, nargs="*")
    args = parser.parse_args()

    stats = {"revisadas": 0, "embed": 0, "video": 0, "foto": 0}

    with SessionLocal() as db:
        q = db.query(ContentProposal).filter(ContentProposal.status.in_(LIVE))
        if args.ids:
            q = q.filter(ContentProposal.id.in_(args.ids))
        props = q.order_by(ContentProposal.id).all()
        logger.info("Propuestas a enriquecer: %d", len(props))

        for p in props:
            stats["revisadas"] += 1
            if not p.body_md:
                continue
            subject = (p.target_keyword or p.title or "").strip()
            changed = False

            # 1. Normaliza enlaces YouTube → embed.
            emb = embed_youtube_links(p.body_md)
            if emb and emb != p.body_md:
                logger.info("[#%s] enlace YouTube → embed", p.id)
                stats["embed"] += 1
                if not args.dry_run:
                    p.body_md = emb
                changed = True

            # 2. Vídeo best-effort si no tiene.
            if not p.video:
                try:
                    from app.services.news_research import find_video
                    vid = find_video(subject, subject) if subject else None
                except Exception as exc:  # noqa: BLE001
                    vid = None
                    logger.warning("[#%s] find_video falló: %s", p.id, exc)
                if vid:
                    logger.info("[#%s] vídeo añadido: %s", p.id, vid.get("title"))
                    stats["video"] += 1
                    if not args.dry_run:
                        p.video = vid
                        url = f"https://www.youtube.com/watch?v={vid['youtube_id']}"
                        if url not in (p.body_md or ""):
                            p.body_md = (p.body_md or "").rstrip() + f"\n\n{url}\n"
                    changed = True

            # 3. Foto (hero) ÚNICA best-effort si no tiene (dedup + arte IA).
            if not p.hero_image_url:
                hero_meta = None
                try:
                    from app.services.blog_hero import build_unique_hero
                    hero_meta = build_unique_hero(db, p.entities or [], subject)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[#%s] foto falló: %s", p.id, exc)
                    hero_meta = None
                if hero_meta:
                    logger.info("[#%s] foto añadida", p.id)
                    stats["foto"] += 1
                    if not args.dry_run:
                        from app.services.hero_io import apply_hero
                        apply_hero(p, hero_meta)  # paquete completo, sin desincronizar
                    changed = True

            if changed and not args.dry_run:
                db.commit()

    logger.info(
        "Enriquecimiento %s: %d revisadas · %d embeds · %d vídeos · %d fotos",
        "[DRY-RUN]" if args.dry_run else "aplicado",
        stats["revisadas"], stats["embed"], stats["video"], stats["foto"],
    )


if __name__ == "__main__":
    main()
