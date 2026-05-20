"""Orquestador: regenera TODO el seo_content del sitio de forma consistente.

Regenera artist → album → song → person → taxonomías (theme/place/concept)
con `force=True`. Como `upsert_seo_content` pone `published=False` al
sobrescribir, este script:

  1. Toma un SNAPSHOT de qué (entity_type, entity_id) estaban publicados.
  2. Regenera todo.
  3. RESTAURA la publicación: lo que estaba publicado vuelve a published;
     las taxonomías (contenido nuevo) se publican también.

Así el sitio nunca se queda sin contenido tras el batch.

Uso:
    python -m scripts.seo.regenerate_all                  # todo
    python -m scripts.seo.regenerate_all --only taxonomy  # solo taxonomías
    python -m scripts.seo.regenerate_all --only song --limit 3   # prueba
    python -m scripts.seo.regenerate_all --dry-run        # lista sin generar
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from openai import OpenAI

from app.config import get_settings
from app.db.models import Album, Artist, Concept, Person, Place, SeoContent, Song, Theme
from scripts.research.common import get_session, log
from scripts.seo.generate_album_content import generate_for_album
from scripts.seo.generate_artist_content import generate_for_artist
from scripts.seo.generate_person_content import generate_for_person
from scripts.seo.generate_song_content import generate_for_song
from scripts.seo.generate_taxonomy_content import generate_for_taxonomy

# orden de procesamiento → (nombre, función, lista de "targets")
PHASES = ["artist", "album", "song", "person", "taxonomy"]


def _collect_targets(db, only: str | None, limit: int | None):
    """Devuelve lista de (phase, *args para la función generadora)."""
    targets: list[tuple] = []

    if only in (None, "artist"):
        for (slug,) in db.query(Artist.slug).order_by(Artist.id).all():
            targets.append(("artist", slug))
    if only in (None, "album"):
        for (slug,) in db.query(Album.slug).order_by(Album.id).all():
            targets.append(("album", slug))
    if only in (None, "song"):
        for (slug,) in db.query(Song.slug).order_by(Song.id).all():
            targets.append(("song", slug))
    if only in (None, "person"):
        for (slug,) in db.query(Person.slug).order_by(Person.id).all():
            targets.append(("person", slug))
    if only in (None, "taxonomy"):
        for kind, model in (("theme", Theme), ("place", Place), ("concept", Concept)):
            for (slug,) in db.query(model.slug).order_by(model.id).all():
                targets.append(("taxonomy", kind, slug))

    if limit is not None:
        targets = targets[:limit]
    return targets


def _run_one(client, db, target: tuple) -> bool:
    phase = target[0]
    if phase == "artist":
        return generate_for_artist(client, db, target[1], force=True)
    if phase == "album":
        return generate_for_album(client, db, target[1], force=True)
    if phase == "song":
        return generate_for_song(client, db, target[1], force=True)
    if phase == "person":
        return generate_for_person(client, db, target[1], force=True)
    if phase == "taxonomy":
        return generate_for_taxonomy(client, db, target[1], target[2], force=True)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=PHASES, help="regenera solo un tipo")
    parser.add_argument("--limit", type=int, help="máximo de piezas (para pruebas)")
    parser.add_argument("--dry-run", action="store_true", help="lista sin generar")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return
    client = OpenAI(api_key=settings.openai_api_key)

    with get_session() as db:
        # 1. SNAPSHOT de lo publicado
        published_before: set[tuple[str, int]] = {
            (et, eid)
            for et, eid in db.query(
                SeoContent.entity_type, SeoContent.entity_id
            ).filter(SeoContent.published.is_(True)).all()
        }
        log(f"Snapshot: {len(published_before)} piezas publicadas antes del batch")

        targets = _collect_targets(db, args.only, args.limit)
        log(f"Targets a regenerar: {len(targets)}")

        if args.dry_run:
            for t in targets:
                print("  ", " ".join(str(x) for x in t))
            return

        # 2. REGENERAR
        ok, fail = 0, 0
        for i, target in enumerate(targets, 1):
            label = " ".join(str(x) for x in target)
            log(f"[{i}/{len(targets)}] {label}")
            try:
                if _run_one(client, db, target):
                    ok += 1
                else:
                    fail += 1
            except Exception as exc:  # noqa: BLE001
                log(f"  ERROR en {label}: {exc}", "err")
                db.rollback()
                fail += 1

        # 3. RESTAURAR publicación
        now = datetime.now(timezone.utc)
        restored = 0
        for et, eid in published_before:
            n = (
                db.query(SeoContent)
                .filter(
                    SeoContent.entity_type == et,
                    SeoContent.entity_id == eid,
                )
                .update({"published": True, "reviewed_at": now})
            )
            restored += n
        # Taxonomías: contenido nuevo, se publica todo
        tax_published = (
            db.query(SeoContent)
            .filter(SeoContent.entity_type.in_(["theme", "place", "concept"]))
            .update({"published": True, "reviewed_at": now}, synchronize_session=False)
        )
        db.commit()

        log(
            f"Terminado. Generados OK: {ok} · Fallos: {fail} · "
            f"Republicados: {restored} · Taxonomías publicadas: {tax_published}"
        )


if __name__ == "__main__":
    main()
