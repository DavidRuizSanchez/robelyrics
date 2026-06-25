"""Revive posts temáticos despublicados con INVESTIGACIÓN WEB DIRIGIDA + dossier.

Algunos posts evergreen eran temáticos (sin entidad) y su tema es una conexión
entre una persona y Robe (Kutxi Romero, Fito Cabrales). El dossier del corpus por
sí solo no traía hechos concretos de esa conexión, así que el rigor los rechazaba.

Aquí, además del dossier, se hace una investigación WEB dirigida a la conexión
(declaraciones, encuentros, colaboraciones), se funde como material real y se
regenera con el motor profundo (que verifica sección a sección: solo sobrevive lo
respaldado, anti-invención). El rigor decide si llega al listón y se republica.

Uso:
    python -m scripts.blog.revive_topical --dry-run
    python -m scripts.blog.revive_topical
"""
from __future__ import annotations

import argparse
import logging

from app.db.models import ContentProposal, Person, Place, Post, Song
from app.db.session import SessionLocal
from app.services.draft_generator import _deep_body
from app.services.editorial_review import review as editorial_review
from app.services.news_research import web_research
from app.services.publishing import auto_publish_post

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# post_id → (model, slug, framing, [consultas web dirigidas a la conexión])
MAP = {
    7: (
        Person, "kutxi-romero",
        "Perfil de Kutxi Romero (cantante de Marea) y su relación REAL con Robe y "
        "Extremoduro: encuentros, declaraciones, homenajes, influencia mutua. Aporta "
        "hechos, fechas y CITAS concretas; nada genérico.",
        [
            "Kutxi Romero sobre Robe Iniesta Extremoduro declaraciones",
            "Kutxi Romero Marea homenaje Robe muerte",
            "Kutxi Romero Robe amistad entrevista anécdota",
            "Marea Extremoduro relación influencia Robe Kutxi",
        ],
    ),
    32: (
        Person, "fito-cabrales",
        "Fito Cabrales (Platero y Tú, Fito & Fitipaldis) y su conexión REAL con Robe: "
        "encuentros, colaboraciones, declaraciones mutuas, influencia. Datos y citas "
        "concretas, canciones nombradas; nada genérico.",
        [
            "Fito Cabrales sobre Robe Iniesta Extremoduro declaraciones",
            "Platero y Tú Extremoduro gira relación Robe Fito",
            "Fito Cabrales Robe colaboración canción homenaje",
            "Fito Cabrales Robe amistad entrevista anécdota",
        ],
    ),
}


# Propuestas (banco) a revivir ancladas a entidad real.
# prop_id → (model, slug, framing, [consultas web])
PROP_MAP = {
    197: (
        Song, "calle-esperanza-s-n",
        "La canción «Calle Esperanza s/n» de Extremoduro (disco 'Material defectuoso', "
        "2011) como HOMENAJE al Umore Ona, el txoko del rock del Casco Viejo de Bilbao. "
        "Cuenta qué era el Umore Ona, su vínculo con Robe y la banda, y qué dice la "
        "canción. Versos y hechos concretos; nada genérico.",
        [
            "Umore Ona Bilbao Extremoduro txoko Robe",
            "Calle Esperanza s/n Extremoduro significado Umore Ona",
            "Umore Ona Casco Viejo Bilbao historia bar rock",
        ],
    ),
    198: (
        Place, "muxika",
        "Muxika (Bizkaia) como refugio creativo de Robe: su casa/estudio en el valle, "
        "qué grabó allí (La Casa de Iñaki), cómo influyó en su obra. Hechos concretos, "
        "discos/canciones nombrados; nada de biografía genérica ni relleno.",
        [
            "Robe Iniesta Muxika Bizkaia casa estudio",
            "La Casa de Iñaki Muxika Extremoduro grabación",
            "Robe Vizcaya refugio retiro vivir",
        ],
    ),
}


def _gather(queries: list[str]) -> str:
    """Investigación web dirigida: snippets reales (vía DataForSEO), deduplicados."""
    hits: list[dict] = []
    for q in queries:
        hits.extend(web_research(q, n=5))
    seen: set[str] = set()
    out: list[str] = []
    for r in hits:
        kref = r.get("url") or r.get("title") or ""
        if kref and kref not in seen:
            seen.add(kref)
            out.append(f"- {r['title']}: {r['snippet']}")
    logger.info("  web dirigida: %d snippets reales", len(out))
    return "\n".join(out[:16])


def _revive_proposals(db, dry_run: bool) -> None:
    """Revive PROPUESTAS del banco ancladas a entidad real: regen profunda +
    investigación web + rigor. Si pasan, quedan 'proposed' mejoradas."""
    et_of = {Song: "song", Place: "place", Person: "person"}
    for prop_id, (model, slug, framing, queries) in PROP_MAP.items():
        p = db.get(ContentProposal, prop_id)
        if not p:
            logger.info("[prop #%s] no existe", prop_id)
            continue
        entity = db.query(model).filter(model.slug == slug).first()
        if not entity:
            logger.info("[prop #%s] entidad %s no encontrada", prop_id, slug)
            continue
        logger.info("[prop #%s] %s → %s/%s", prop_id, p.title, et_of[model], slug)
        if dry_run:
            continue
        extra = _gather(queries)
        payload = _deep_body(db, entity_type=et_of[model], entity=entity,
                             framing=framing, extra_material=extra)
        if not payload or not payload.get("body_md"):
            logger.info("  no se pudo regenerar (sin material)")
            continue
        body = payload["body_md"]
        v = editorial_review(body, kind=p.kind,
                             subject=(p.target_keyword or p.title or "").strip())
        if v.verdict == "reject":
            logger.info("  sigue sin llegar (score %d): %s → se queda como está",
                        v.score, "; ".join(v.reasons))
            continue
        if v.verdict == "revise" and v.tightened_body_md:
            body = v.tightened_body_md
        p.body_md = body
        p.title = (payload.get("title") or p.title)[:240]
        p.excerpt = payload.get("excerpt") or p.excerpt
        if payload.get("meta_title"):
            p.meta_title = payload["meta_title"][:60]
        if payload.get("meta_description"):
            p.meta_description = payload["meta_description"][:155]
        db.commit()
        logger.info("  ✓ revivida (score %d) → propuesta #%s mejorada", v.score, prop_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--proposals", action="store_true",
                        help="revivir propuestas del banco (197/198) en vez de posts")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.proposals:
            _revive_proposals(db, args.dry_run)
            return
        for post_id, (model, slug, framing, queries) in MAP.items():
            post = db.get(Post, post_id)
            if not post:
                logger.info("[post #%s] no existe", post_id)
                continue
            entity = db.query(model).filter(model.slug == slug).first()
            if not entity:
                logger.info("[post #%s] entidad %s no encontrada", post_id, slug)
                continue
            logger.info("[post #%s] %s → %s", post_id, post.title, slug)
            if args.dry_run:
                continue

            extra = _gather(queries)
            payload = _deep_body(db, entity_type="person", entity=entity,
                                 framing=framing, extra_material=extra)
            if not payload or not payload.get("body_md"):
                logger.info("  no se pudo regenerar (sin material)")
                continue
            body = payload["body_md"]
            v = editorial_review(body, kind="evergreen",
                                 subject=(post.target_keyword or post.title or "").strip())
            if v.verdict == "reject":
                logger.info("  sigue sin llegar (score %d): %s → queda en revisión",
                            v.score, "; ".join(v.reasons))
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
