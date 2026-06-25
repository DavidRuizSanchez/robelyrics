"""Revive posts temáticos despublicados ANCLÁNDOLOS a una entidad real concreta.

Algunos posts evergreen eran SEO-articles temáticos (sin source_id de entidad)
pero su TEMA sí es una entidad de nuestro corpus (p.ej. una persona). Aquí se
mapea cada post a su entidad y se regenera con el MOTOR PROFUNDO (dossier RAG),
se pasa por el rigor y, si llega al listón, se REPUBLICA.

Mapa hardcodeado (one-shot puntual). Uso:
    python -m scripts.blog.revive_topical --dry-run
    python -m scripts.blog.revive_topical
"""
from __future__ import annotations

import argparse
import logging

from app.db.models import Band, Person, Post
from app.db.session import SessionLocal
from app.services.draft_generator import _deep_body
from app.services.editorial_review import review as editorial_review
from app.services.publishing import auto_publish_post

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# post_id → (entity_type, model, slug, framing)
MAP = {
    7: ("person", Person, "kutxi-romero",
        "Perfil de Kutxi Romero (cantante de Marea) y su relación REAL con Robe y "
        "Extremoduro: encuentros, declaraciones, homenajes, influencia mutua. "
        "Aporta hechos, fechas y CITAS concretas; nada genérico ni de relleno."),
    32: ("person", Person, "fito-cabrales",
         "Fito Cabrales (Platero y Tú, Fito & Fitipaldis) y su conexión REAL con "
         "Robe: encuentros, colaboraciones, declaraciones, influencia. Datos y citas "
         "concretas, canciones nombradas; nada genérico."),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as db:
        for post_id, (etype, model, slug, framing) in MAP.items():
            post = db.get(Post, post_id)
            if not post:
                logger.info("[post #%s] no existe", post_id)
                continue
            entity = db.query(model).filter(model.slug == slug).first()
            if not entity:
                logger.info("[post #%s] entidad %s/%s no encontrada", post_id, etype, slug)
                continue
            logger.info("[post #%s] %s → %s/%s", post_id, post.title, etype, slug)
            if args.dry_run:
                continue

            payload = _deep_body(db, entity_type=etype, entity=entity, framing=framing)
            if not payload or not payload.get("body_md"):
                logger.info("  no se pudo regenerar (sin material)")
                continue
            body = payload["body_md"]
            v = editorial_review(body, kind="evergreen",
                                 subject=(post.target_keyword or post.title or "").strip())
            if v.verdict == "reject":
                logger.info("  sigue sin llegar (score %d) → queda en revisión", v.score)
                continue
            if v.verdict == "revise" and v.tightened_body_md:
                body = v.tightened_body_md
            post.body_md = body
            post.title = (payload.get("title") or post.title)[:240]
            post.excerpt = payload.get("excerpt") or post.excerpt
            auto_publish_post(db, post, factcheck=False, rigor=False)
            logger.info("  ✓ republicado (score %d): /blog/%s", v.score, post.slug)


if __name__ == "__main__":
    main()
