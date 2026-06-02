"""Remate de la regeneración a la voz nueva: personas, grupos, taxonomías y
posts NO-noticia (evergreen/efeméride/editorial). Regenera por elemento y
REPUBLICA al vuelo (cada página está en borrador solo unos segundos).

- Personas/grupos/taxonomías: sus generadores reales (con destilado donde
  aplique) → seo_content nuevo → republicar.
- Posts sin fuente externa: revoice (reescribe el cuerpo existente en la voz
  nueva, mismos hechos, sin inventar) in situ.

Uso:
  python -m scripts.seo.regen_extras                 # todo
  python -m scripts.seo.regen_extras --only persons  # persons|bands|taxonomies|posts
"""
from __future__ import annotations

import argparse

from openai import OpenAI
from sqlalchemy import text

from app.config import get_settings
from app.db.models import Concept, Person, Place, Post, Band, Theme
from app.services.content_generator import revoice_post
from app.services.entity_resolver import (
    autolink_corpus,
    build_corpus_index,
    load_link_stats,
)
from app.services.text_sanitizer import normalize_headings
from scripts.research.common import get_session, log
from scripts.seo.generate_band_content import generate_for_band
from scripts.seo.generate_person_content import generate_for_person
from scripts.seo.generate_taxonomy_content import generate_for_taxonomy


def _republish(db, entity_type: str, slug: str) -> None:
    db.execute(text(
        "UPDATE seo_content SET published=true, reviewed_at=now() "
        "WHERE entity_type=:t AND slug=:s"
    ), {"t": entity_type, "s": slug})
    db.commit()


def _do(client, slugs, gen_fn, entity_type, label):
    log(f"=== {label}: {len(slugs)} ===")
    for s in slugs:
        with get_session() as db:
            try:
                gen_fn(client, db, s, force=True)
            except Exception as e:  # noqa: BLE001
                log(f"  fallo {entity_type} {s}: {e}", "err")
        with get_session() as db:
            _republish(db, entity_type, s)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", choices=["persons", "bands", "taxonomies", "posts"])
    args = ap.parse_args()

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    if args.only in (None, "persons"):
        with get_session() as db:
            slugs = [p.slug for p in db.query(Person).order_by(Person.id).all()]
        _do(client, slugs, generate_for_person, "person", "PERSONAS")

    if args.only in (None, "bands"):
        with get_session() as db:
            slugs = [b.slug for b in db.query(Band).order_by(Band.id).all()]
        _do(client, slugs, generate_for_band, "band", "GRUPOS")

    if args.only in (None, "taxonomies"):
        for kind, model in (("theme", Theme), ("place", Place), ("concept", Concept)):
            with get_session() as db:
                slugs = [r.slug for r in db.query(model).order_by(model.id).all()]
            log(f"=== TAXONOMÍA {kind}: {len(slugs)} ===")
            for s in slugs:
                with get_session() as db:
                    try:
                        generate_for_taxonomy(client, db, kind, s, force=True)
                    except Exception as e:  # noqa: BLE001
                        log(f"  fallo {kind} {s}: {e}", "err")
                with get_session() as db:
                    _republish(db, kind, s)

    if args.only in (None, "posts"):
        with get_session() as db:
            post_ids = [
                p.id for p in db.query(Post)
                .filter(Post.status == "published", Post.source_url.is_(None))
                .all()
            ]
        log(f"=== POSTS no-noticia (revoice): {len(post_ids)} ===")
        for pid in post_ids:
            with get_session() as db:
                p = db.get(Post, pid)
                if not p or not p.body_md:
                    continue
                out = revoice_post(title=p.title, body_md=p.body_md)
                nb = out.get("body_md") or ""
                if not nb or len(nb) < 300:
                    log(f"  revoice corto, se salta {p.slug}", "warn")
                    continue
                nb = normalize_headings(nb) or nb
                nb = autolink_corpus(
                    nb, build_corpus_index(db), max_links=4,
                    exclude_slug=p.slug, link_stats=load_link_stats(),
                )
                p.title = out["title"][:240]
                p.excerpt = (out.get("excerpt") or p.excerpt or "")[:200]
                p.body_md = nb
                p.meta_title = (out.get("meta_title") or p.meta_title or "")[:60]
                p.meta_description = (out.get("meta_description") or p.meta_description or "")[:155]
                if out.get("entities"):
                    p.entities = out["entities"]
                db.commit()
                log(f"  ✓ revoice {p.slug}", "ok")

    log("REGEN EXTRAS completado", "ok")


if __name__ == "__main__":
    main()
