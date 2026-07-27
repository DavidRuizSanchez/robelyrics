"""Auditoría y arreglo de imágenes hero YA publicadas.

Pasa el gate de relevancia (`hero_guard.verify_hero`, visión gpt-4o) sobre los
posts publicados y detecta los que llevan una imagen que NO muestra a su sujeto
(el caso Rosendo: un óleo de una mujer con el crédito de Robe). Opcionalmente
corrige: regenera el hero a una imagen relevante (arte propio si no hay foto real
verificable) de forma coherente (los 5 campos juntos).

Modos:
  --scan                 Reporta el veredicto de cada post publicado con imagen.
  --scan --slugs A B     Solo esos slugs.
  --scan --limit N       Acota el nº de posts (control de coste de visión).
  --fix --slugs A B      Regenera el hero de esos posts (con gate). Empieza aquí
                         para un arreglo quirúrgico (p.ej. Rosendo).
  --fix --failing        Regenera TODOS los que fallan el gate (auditar + arreglar).
  --entities             Audita también las imágenes de Person/Band/Artist vs su
                         nombre (pilla desincronías de fetch_entity_images --rehost).

SIEMPRE hace backup por stdout de los valores viejos antes de tocar nada.
"""
from __future__ import annotations

import argparse
import logging

from app.db.models import Post
from app.db.session import SessionLocal
from app.services.blog_hero import build_unique_hero, used_hero_urls
from app.services.hero_guard import verify_hero
from app.services.hero_io import apply_hero, read_hero

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _subject(post: Post) -> str:
    return (post.target_keyword or post.title or "").strip()


def _published_with_hero(db, slugs: list[str] | None, limit: int | None):
    q = db.query(Post).filter(Post.status == "published").filter(Post.hero_image_url.isnot(None))
    if slugs:
        q = q.filter(Post.slug.in_(slugs))
    q = q.order_by(Post.published_at.desc().nullslast())
    if limit:
        q = q.limit(limit)
    return q.all()


def _scan(db, slugs, limit) -> list[Post]:
    posts = _published_with_hero(db, slugs, limit)
    failing: list[Post] = []
    logger.info("Auditando %d post(s) publicados con imagen…", len(posts))
    for p in posts:
        v = verify_hero(read_hero(p), subject=_subject(p), entities=p.entities or [])
        mark = "OK " if v.ok else "✗✗ "
        logger.info("  %s%-45s | %s%s", mark, p.slug[:45],
                    v.reason, f" [ve: {v.describes}]" if v.describes else "")
        if not v.ok:
            failing.append(p)
    logger.info("Resultado: %d/%d fallan el gate de relevancia.", len(failing), len(posts))
    return failing


def _fix(db, posts: list[Post]) -> None:
    if not posts:
        logger.info("Nada que arreglar.")
        return
    for p in posts:
        old = read_hero(p)
        used = used_hero_urls(db) - {p.hero_image_url} if p.hero_image_url else used_hero_urls(db)
        new_hero = build_unique_hero(
            db, p.entities or [], _subject(p), used=used, alt_label=p.title,
        )
        logger.info("[fix] %s", p.slug)
        logger.info("      BACKUP viejo: %s", old)
        logger.info("      NUEVO:        %s", new_hero)
        apply_hero(p, new_hero)
        db.commit()


def _audit_entities(db) -> None:
    """Chequeo de relevancia de las imágenes de entidad (Person/Band/Artist) vs su
    nombre. Solo REPORTA (no corrige: la corrección de entidades va por
    fetch_entity_images)."""
    from app.db.models import Artist, Band, Person

    checks = [
        (Person, lambda e: (e.stage_name or e.full_name or e.slug)),
        (Band, lambda e: (e.name or e.slug)),
        (Artist, lambda e: (e.name or e.slug)),
    ]
    for model, namer in checks:
        rows = db.query(model).filter(model.image_url.isnot(None)).all()
        logger.info("Entidades %s con imagen: %d", model.__name__, len(rows))
        for e in rows:
            name = namer(e)
            hero = {"url": e.image_url, "attribution": e.image_attribution,
                    "license": e.image_license, "source": e.image_source_url}
            v = verify_hero(hero, subject=name, entities=[{"label": name}])
            if not v.ok:
                logger.warning("  ✗ %s/%s: %s (ve: %s) | %s",
                               model.__name__, e.slug, v.reason, v.describes, e.image_url)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--failing", action="store_true",
                    help="con --fix: arregla TODOS los que fallan el gate")
    ap.add_argument("--entities", action="store_true")
    ap.add_argument("--slugs", nargs="*")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    with SessionLocal() as db:
        if args.entities:
            _audit_entities(db)
        if args.fix:
            if args.failing:
                targets = _scan(db, args.slugs, args.limit)
            elif args.slugs:
                targets = _published_with_hero(db, args.slugs, None)
            else:
                ap.error("--fix requiere --slugs <...> o --failing")
                return
            _fix(db, targets)
        elif args.scan:
            _scan(db, args.slugs, args.limit)
        elif not args.entities:
            ap.error("indica un modo: --scan | --fix | --entities")


if __name__ == "__main__":
    main()
