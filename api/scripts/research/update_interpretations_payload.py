"""Actualiza el campo `song_ids` en los payloads de Qdrant `interpretations_v1`
sin re-embedear. Útil tras ejecutar `link_sources_to_songs.py`.

Ejecución:
  docker compose exec api python -m scripts.research.update_interpretations_payload
"""
from __future__ import annotations

from qdrant_client.http.models import FieldCondition, Filter, MatchValue

from app.db.models import InterpretationSource
from app.services.qdrant_client import get_qdrant
from scripts.research.common import get_session, log

COLLECTION = "interpretations_v1"


def main() -> None:
    qdrant = get_qdrant()
    n_updated = 0
    n_sources = 0

    with get_session() as db:
        sources = (
            db.query(InterpretationSource)
            .filter(InterpretationSource.referenced_song_ids.isnot(None))
            .all()
        )
        log(f"sources con referenced_song_ids: {len(sources)}")

        for src in sources:
            song_ids = list(src.referenced_song_ids or [])
            # Update sólo los puntos cuyo payload.source_id == src.id
            qdrant.set_payload(
                collection_name=COLLECTION,
                payload={"song_ids": song_ids},
                points=Filter(
                    must=[FieldCondition(key="source_id", match=MatchValue(value=src.id))]
                ),
            )
            n_sources += 1
            n_updated += 1  # no sabemos cuántos points por source pero sí cuántas sources

    log(f"sources con payload actualizado: {n_updated}", "ok")


if __name__ == "__main__":
    main()
