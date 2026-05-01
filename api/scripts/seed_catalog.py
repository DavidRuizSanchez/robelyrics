"""Siembra artists + albums desde data/discography.yaml.

NO toca songs (eso es Fase 1, ingesta de letras desde Genius).

Ejecutar: docker compose exec api python -m scripts.seed_catalog
Idempotente: si ya existen, los actualiza.
"""
from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import Album, Artist
from scripts.research.common import get_session, load_discography, log


def main() -> None:
    data = load_discography()
    artists = data.get("artists", [])
    if not artists:
        log("discography.yaml vacío o sin clave 'artists'", "err")
        return

    with get_session() as db:
        for art in artists:
            slug = art["slug"]
            stmt = (
                pg_insert(Artist)
                .values(
                    slug=slug,
                    name=art["name"],
                    active_years=art.get("active_years"),
                )
                .on_conflict_do_update(
                    index_elements=["slug"],
                    set_={"name": art["name"], "active_years": art.get("active_years")},
                )
                .returning(Artist.id)
            )
            artist_id = db.execute(stmt).scalar_one()
            log(f"artist {slug} → id={artist_id}", "ok")

            for alb in art.get("albums", []):
                alb_stmt = (
                    pg_insert(Album)
                    .values(
                        artist_id=artist_id,
                        title=alb["title"],
                        slug=alb["slug"],
                        year=alb["year"],
                        kind=alb.get("kind", "studio"),
                    )
                    .on_conflict_do_update(
                        constraint="uq_albums_artist_slug",
                        set_={
                            "title": alb["title"],
                            "year": alb["year"],
                            "kind": alb.get("kind", "studio"),
                        },
                    )
                    .returning(Album.id)
                )
                album_id = db.execute(alb_stmt).scalar_one()
                log(f"  album {alb['slug']} ({alb['year']}) → id={album_id}")

    log("Catálogo sembrado", "ok")


if __name__ == "__main__":
    main()
