"""Pobla `interpretation_sources.referenced_song_ids` detectando menciones
de canciones en `content_clean`.

Usa el matcher `find_referenced_titles` de common.py (case+accent insensitive,
con word boundaries para evitar falsos matches).

Tras ejecutar esto, conviene re-correr `embed_interpretations.py` para que
los payloads en Qdrant `interpretations_v1` reflejen los nuevos song_ids
(el boost del canal interpretations en /search/semantic se basa en eso).

Ejecución:
  docker compose exec api python -m scripts.research.link_sources_to_songs
"""
from __future__ import annotations

import argparse

from sqlalchemy import update

from app.db.models import InterpretationSource, Song
from scripts.research.common import find_referenced_titles, get_session, log


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Reescribir aunque ya tenga referenced_song_ids")
    args = parser.parse_args()

    with get_session() as db:
        # Cargar todos los títulos canónicos
        all_titles = [(s.id, s.title) for s in db.query(Song).all()]
        log(f"songs en catálogo: {len(all_titles)}")

        # Cargar sources con content_clean
        q = db.query(InterpretationSource).filter(InterpretationSource.content_clean.isnot(None))
        sources = q.all()
        log(f"sources con contenido: {len(sources)}")

        n_updated = 0
        n_skipped = 0
        n_with_songs = 0
        total_links = 0

        for src in sources:
            if not args.force and src.referenced_song_ids:
                n_skipped += 1
                continue

            song_ids = find_referenced_titles(src.content_clean or "", all_titles)
            if song_ids:
                n_with_songs += 1
                total_links += len(song_ids)

            # UPDATE incluso si song_ids está vacío para marcar que se procesó
            db.execute(
                update(InterpretationSource)
                .where(InterpretationSource.id == src.id)
                .values(referenced_song_ids=song_ids or None)
            )
            n_updated += 1

    log(
        f"updated: {n_updated} · skipped: {n_skipped} · "
        f"with-songs: {n_with_songs} · total links: {total_links}",
        "ok",
    )


if __name__ == "__main__":
    main()
