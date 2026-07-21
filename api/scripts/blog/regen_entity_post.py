"""Regenera un post anclado a ENTIDAD/TEMA (evergreen, spotlight, album-anniversary)
con el pipeline NUEVO: motor profundo RAG + tier de engagement (más extensión y
brief SERP en premium/flagship) + imagen hero ÚNICA con ALT + vídeos + gate de
VERACIDAD determinista (citas de letra + atribuciones álbum/año).

A diferencia de `regen_one_post` (solo noticias con source_url), este cubre los
posts anclados al corpus. Reconstruye una ContentProposal transitoria a partir del
post y de los args (kind/source_type/source_id) y corre `generate_proposal_draft`.

DRY-RUN por defecto: genera y AUDITA, sin tocar el post. Con --apply actualiza el
post in situ y lo deja en `pending_review` (reconstrucción supervisada: el admin lo
revisa y republica).

Uso:
  python -m scripts.blog.regen_entity_post --slug <slug> --kind evergreen \
      --source-type theme --source-id 1            # dry-run
  python -m scripts.blog.regen_entity_post --slug <slug> ... --apply
"""
from __future__ import annotations

import argparse
import logging

from app.db.models import ContentProposal, Post
from app.db.session import SessionLocal
from app.services.draft_generator import generate_proposal_draft
from app.services.fact_check import check_body
from app.services.lyric_guard import check_lyrics

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def regen(db, post: Post, *, kind: str, source_type: str | None,
          source_id: int | None, apply: bool, tier: str | None = None) -> bool:
    # Propuesta TEMPORAL que espeja el post; el pipeline nuevo la rellena (cuerpo
    # profundo + tier + hero + vídeos). Se persiste durante la generación (el
    # pipeline hace commit/refresh) y se elimina al final: el contenido va al post.
    # Propuesta TRANSITORIA (no se añade a la sesión → no persiste, no choca con la
    # constraint única kind/source y no deja filas sueltas). persist=False evita el
    # commit/refresh finales; leemos los campos generados en memoria.
    p = ContentProposal(
        kind=kind,
        source_type=source_type,
        source_id=source_id,
        title=post.title,
        target_keyword=post.target_keyword,
        search_volume=None,
        entities=post.entities or [],
        # Estos posts curados son de alto interés: se puede forzar el tier para que
        # salgan con la extensión/profundidad que la temática merece.
        quality_tier=tier,
        status="proposed",
    )
    if not generate_proposal_draft(db, p, persist=False):
        logger.error("  ✗ %s: la generación no produjo cuerpo", post.slug)
        return False

    g = {
        "excerpt": p.excerpt, "body_md": p.body_md or "", "meta_title": p.meta_title,
        "meta_description": p.meta_description, "entities": p.entities,
        "hero_image_url": p.hero_image_url, "hero_image_alt": p.hero_image_alt,
        "hero_image_attribution": p.hero_image_attribution,
        "hero_image_license": p.hero_image_license,
        "hero_image_source_url": p.hero_image_source_url,
        "video": p.video, "videos": p.videos,
        "engagement_score": p.engagement_score, "quality_tier": p.quality_tier,
    }

    # GATE DE VERACIDAD (el mismo que en publicación): nada con citas inventadas
    # ni atribuciones erróneas.
    lyr = check_lyrics(db, g["body_md"])
    rep = check_body(db, g["body_md"], use_web=False)
    veraz = not lyr.blocking and not lyr.to_review and not rep.autofixes
    words = len(g["body_md"].split())

    print(f"\n{'=' * 70}\nPOST: {post.slug}")
    print(f"  tier={g['quality_tier']} score={g['engagement_score']} · {words} palabras "
          f"(antes {len((post.body_md or '').split())})")
    print(f"  hero={'sí' if g['hero_image_url'] else 'NO'} | alt={g['hero_image_alt']!r}")
    print(f"  vídeos={len(g['videos'] or [])}")
    print(f"  VERACIDAD: {'✅ limpio' if veraz else '⚠️ REVISAR'} "
          f"(citas bloq={len(lyr.blocking)}, revisar={len(lyr.to_review)}, "
          f"álbum/año={len(rep.autofixes)})")
    for v in lyr.blocking + lyr.to_review:
        print(f"    - cita {v.status}: «{v.quote[:50]}» → {v.reason}")
    for v in rep.autofixes:
        print(f"    - álbum/año: {v.evidence}")
    print("  ---BODY (primeros 2000)---\n" + g["body_md"][:2000])

    if not apply:
        return True
    if not veraz:
        logger.warning("  ✗ %s: NO se aplica (no pasa veracidad)", post.slug)
        return False

    # Se conserva el TÍTULO original (keyword SEO curada); se renueva el cuerpo.
    post.excerpt = g["excerpt"]
    post.body_md = g["body_md"]
    post.meta_title = (g["meta_title"] or None)
    post.meta_description = (g["meta_description"] or None)
    post.entities = g["entities"] or post.entities
    post.hero_image_url = g["hero_image_url"]
    post.hero_image_alt = g["hero_image_alt"]
    post.hero_image_attribution = g["hero_image_attribution"]
    post.hero_image_license = g["hero_image_license"]
    post.hero_image_source_url = g["hero_image_source_url"]
    post.video = g["video"]
    post.videos = g["videos"]
    post.engagement_score = g["engagement_score"]
    post.quality_tier = g["quality_tier"]
    post.status = "pending_review"  # reconstrucción supervisada
    db.commit()
    logger.info("  ✓ %s actualizado → pending_review", post.slug)
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--kind", required=True,
                    choices=("evergreen", "spotlight", "album-anniversary", "anniversary"))
    ap.add_argument("--source-type", choices=("song", "album", "theme", "place", "concept"))
    ap.add_argument("--source-id", type=int)
    ap.add_argument("--tier", choices=("standard", "premium", "flagship"),
                    help="Fuerza el tier (posts curados de alto interés). Si se omite, "
                         "se calcula por engagement.")
    ap.add_argument("--apply", action="store_true", help="Escribe el post (si no, dry-run).")
    args = ap.parse_args()

    with SessionLocal() as db:
        post = db.query(Post).filter(Post.slug == args.slug).first()
        if not post:
            ap.error(f"no existe el post {args.slug}")
            return
        regen(db, post, kind=args.kind, source_type=args.source_type,
              source_id=args.source_id, apply=args.apply, tier=args.tier)


if __name__ == "__main__":
    main()
