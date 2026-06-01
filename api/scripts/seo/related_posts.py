"""Posts del blog más relevantes por página SEO (módulo "En el diario").

Para cada entidad con seo_content publicado (artista, álbum, canción, persona,
tema, lugar, concepto) calcula los HASTA 3 posts del blog más relevantes,
combinando dos señales (híbrido):
  - Mención explícita: el post nombra la entidad (entities.slug_hint) → fuerte.
  - Semántica: similitud coseno entre el cuerpo de la página y el post
    (embeddings text-embedding-3-large en Qdrant, colección posts_v1).

Escribe `data/related_posts.json` ({ "<tipo>:<slug>": ["post-slug", …] }).
El `/app/data` va read-only en prod: escribe a /tmp y se copia a data/.

Pensado para correr semanalmente (cron). Uso:
  python -m scripts.seo.related_posts
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from qdrant_client.http.models import Distance, PointStruct, VectorParams

from app.db.models import (
    Album, Artist, Concept, Person, Place, Post, SeoContent, Song, Theme,
)
from app.db.session import SessionLocal
from app.services.embeddings import EMBED_DIM, get_embedder
from app.services.qdrant_client import get_qdrant

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUT_PATH = Path("/tmp/related_posts.json")
COLLECTION = "posts_v1"
MAX_LINKS = 3
MIN_SCORE = 0.35          # umbral: por debajo no se considera relevante
W_MENTION = 1.0           # peso de la mención explícita
W_SEMANTIC = 0.6          # peso de la similitud semántica (coseno 0..1)

_MODELS = {
    "artist": Artist, "album": Album, "song": Song, "person": Person,
    "theme": Theme, "place": Place, "concept": Concept,
}


def _ensure_collection(qdrant) -> None:
    existing = {c.name for c in qdrant.get_collections().collections}
    if COLLECTION not in existing:
        qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        logger.info("colección creada: %s", COLLECTION)


def _embed_posts(db, qdrant, embedder, posts) -> None:
    """(Re)embebe los posts publicados en posts_v1."""
    points = []
    for p in posts:
        text = f"{p.title}\n\n{(p.body_md or '')[:6000]}"
        vec = embedder.embed_one(text)
        points.append(PointStruct(id=p.id, vector=vec, payload={"slug": p.slug}))
    if points:
        qdrant.upsert(collection_name=COLLECTION, points=points)
    logger.info("posts embebidos: %d", len(points))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    qdrant = get_qdrant()
    embedder = get_embedder()
    _ensure_collection(qdrant)

    result: dict[str, list[str]] = {}
    with SessionLocal() as db:
        posts = db.query(Post).filter(Post.status == "published").all()
        if not posts:
            logger.info("no hay posts publicados; nada que relacionar")
            return
        _embed_posts(db, qdrant, embedder, posts)
        post_slug_by_id = {p.id: p.slug for p in posts}

        seo_rows = db.query(SeoContent).filter(SeoContent.published.is_(True)).all()
        logger.info("páginas SEO publicadas: %d", len(seo_rows))

        for seo in seo_rows:
            model = _MODELS.get(seo.entity_type)
            if model is None:
                continue
            ent = db.get(model, seo.entity_id)
            if ent is None:
                continue
            slug = ent.slug
            scores: dict[int, float] = {}

            # 1) Mención explícita (entities.slug_hint == slug)
            mentioning = (
                db.query(Post.id)
                .filter(
                    Post.status == "published",
                    Post.entities.contains([{"slug_hint": slug}]),
                )
                .all()
            )
            for (pid,) in mentioning:
                scores[pid] = scores.get(pid, 0.0) + W_MENTION

            # 2) Semántica: cuerpo de la página → vecinos en posts_v1
            body = (seo.body_md or ent.__dict__.get("description") or "")[:4000]
            if body.strip():
                try:
                    qvec = embedder.embed_one(f"{getattr(ent, 'name', slug)}\n\n{body}")
                    hits = qdrant.query_points(
                        collection_name=COLLECTION, query=qvec, limit=8,
                        with_payload=True,
                    ).points
                    for h in hits:
                        pid = int(h.id)
                        cos = max(0.0, float(h.score))
                        scores[pid] = scores.get(pid, 0.0) + W_SEMANTIC * cos
                except Exception as exc:  # noqa: BLE001
                    logger.warning("  semántica falló para %s:%s (%s)",
                                   seo.entity_type, slug, exc)

            ranked = sorted(
                ((pid, sc) for pid, sc in scores.items() if sc >= MIN_SCORE),
                key=lambda kv: kv[1], reverse=True,
            )[:MAX_LINKS]
            if ranked:
                result[f"{seo.entity_type}:{slug}"] = [
                    post_slug_by_id[pid] for pid, _ in ranked
                ]

    if args.dry_run:
        logger.info("[dry-run] %d páginas con posts relacionados", len(result))
        for k, v in list(result.items())[:20]:
            logger.info("  %s -> %s", k, v)
        return

    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    logger.info("Escrito %s · %d páginas con posts relacionados", OUT_PATH, len(result))


if __name__ == "__main__":
    main()
