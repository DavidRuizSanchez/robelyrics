"""Propagación viva (F2.2 / F2.3 del vuelco editorial).

Cuando el corpus cambia (una letra corregida por el MCV, un crédito de autoría
nuevo, una entidad nueva), hay que refrescar SOLO lo afectado para que el site esté
siempre al día: embeddings (buscador, consultorio, listas por mood, "canciones
similares"), grafo de conocimiento y enlazado interno.

El problema que resuelve: `embed_lyrics`/`embed_full_lyrics` no estaban en ningún
cron, así que al corregir una letra el buscador seguía leyendo la vieja. Aquí el
refresco se dispara EN EL MOMENTO del cambio (acotado a la canción), y además se
añade una red de seguridad nocturna en el cron.

Diseño:
- `refresh_song_embeddings(db, song_id)`: re-embebe lines/chunks/full de UNA canción
  (barato, reutiliza las primitivas de scripts.embed_lyrics/embed_full_lyrics).
- `propagate(db, kind, **ctx)`: despachador por tipo de cambio; hace lo scoped inline
  y deja marcado lo pesado (grafo/relink) para el barrido nocturno idempotente.

Nunca lanza: un fallo de refresco no debe tumbar la corrección que lo disparó.
"""
from __future__ import annotations

import logging

from app.config import get_settings

logger = logging.getLogger(__name__)


def refresh_song_embeddings(db, song_id: int) -> bool:
    """Re-embebe a Qdrant lines_v1/chunks_v1/lyrics_full_v1 de una canción. Idempotente
    (ids deterministas). Devuelve True si refrescó algo."""
    settings = get_settings()
    if not getattr(settings, "openai_api_key", None):
        logger.warning("[freshness] sin OPENAI_API_KEY; no se re-embebe canción %s", song_id)
        return False
    try:
        from openai import OpenAI
        from qdrant_client import QdrantClient
        from qdrant_client.http.models import PointStruct

        from app.db.models import Chunk, Line, Song
        from scripts.embed_full_lyrics import (
            COLLECTION as COLL_FULL,
            MAX_CHARS,
            ensure_collection as ensure_full,
        )
        from scripts.embed_full_lyrics import stable_id as full_id
        from scripts.embed_lyrics import (
            COLL_CHUNKS,
            COLL_LINES,
            EMBED_MODEL,
            context_for_song,
            embed_batch,
            ensure_collections,
            stable_id,
        )

        song = db.get(Song, song_id)
        if not song:
            return False
        openai = OpenAI(api_key=settings.openai_api_key)
        qdrant = QdrantClient(url=settings.qdrant_url)
        ensure_collections(qdrant)
        ensure_full(qdrant)
        ctx = context_for_song(song)

        lines = db.query(Line).filter(Line.song_id == song_id).all()
        if lines:
            vecs = embed_batch(openai, [ln.text for ln in lines])
            qdrant.upsert(collection_name=COLL_LINES, points=[
                PointStruct(id=stable_id("line", ln.id), vector=v, payload={
                    **ctx, "line_index": ln.line_index,
                    "stanza_index": ln.stanza_index, "text": ln.text,
                }) for ln, v in zip(lines, vecs, strict=True)
            ])

        chunks = db.query(Chunk).filter(Chunk.song_id == song_id).all()
        if chunks:
            vecs = embed_batch(openai, [c.text for c in chunks])
            qdrant.upsert(collection_name=COLL_CHUNKS, points=[
                PointStruct(id=stable_id("chunk", c.id), vector=v, payload={
                    **ctx, "start_line_index": c.start_line_index,
                    "end_line_index": c.end_line_index, "text": c.text,
                }) for c, v in zip(chunks, vecs, strict=True)
            ])

        full = (song.lyrics_clean or "").strip()
        if len(full) >= 30:
            vec = embed_batch(openai, [full[:MAX_CHARS]])[0]
            qdrant.upsert(collection_name=COLL_FULL, points=[PointStruct(
                id=full_id(song_id), vector=vec,
                payload={**ctx, "song_ids": [song_id], "kind": "lyrics_full"},
            )])
        logger.info("[freshness] canción %s re-embebida (%d lines, %d chunks + full)",
                    song_id, len(lines), len(chunks))
        return True
    except Exception as exc:  # noqa: BLE001 — nunca tumbar la corrección por el refresco
        logger.warning("[freshness] fallo re-embebiendo canción %s: %s", song_id, exc)
        return False


# Marca de que el grafo/enlazado necesitan reconstruirse (lo consume el barrido
# nocturno, que corre build_graph idempotente). Módulo-local: basta para una corrida.
_graph_dirty = False


def mark_graph_dirty() -> None:
    global _graph_dirty
    _graph_dirty = True


def graph_is_dirty() -> bool:
    return _graph_dirty


def propagate(db, kind: str, *, song_id: int | None = None) -> None:
    """Despacha el refresco mínimo según el tipo de cambio.

    - 'lyric'      → re-embed de la canción (buscador/consultorio/listas al día).
    - 'authorship' → re-embed (por si la letra se cita) + marca grafo sucio
                     (aristas lyrics_by/music_by/adapted_from las repone build_graph).
    - 'entity'     → marca grafo sucio (relink_existing lo enlaza en contenido viejo).
    """
    if kind in ("lyric", "authorship") and song_id:
        refresh_song_embeddings(db, song_id)
    if kind in ("authorship", "entity"):
        mark_graph_dirty()
