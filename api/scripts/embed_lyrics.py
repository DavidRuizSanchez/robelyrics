"""Embeddings de letras (lines + chunks) → Qdrant `lines_v1` y `chunks_v1`.

Para cada Line / Chunk en BD:
  1. Embed con OpenAI text-embedding-3-large (3072 dim).
  2. Upsert a la colección Qdrant correspondiente.

Payload Qdrant:
  lines_v1:  {song_id, line_index, text, artist_slug, album_slug, song_title, year}
  chunks_v1: + start_line_index, end_line_index

Idempotencia: id determinista a partir de (kind, db_pk) → re-correr no
duplica. Coste estimado para todo el corpus (~5K líneas + ~1.5K chunks):
~30K tokens de embeddings × $0.13/M = $0.004. Ridículo.

Ejecución:
  docker compose exec api python -m scripts.embed_lyrics
  docker compose exec api python -m scripts.embed_lyrics --only lines
"""
from __future__ import annotations

import argparse
import hashlib

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from app.config import get_settings
from app.db.models import Album, Artist, Chunk, Line, Song
from scripts.research.common import get_session, log

EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 3072
COLL_LINES = "lines_v1"
COLL_CHUNKS = "chunks_v1"


def stable_id(kind: str, pk: int) -> int:
    """ID determinista de 63 bits para Qdrant."""
    h = hashlib.sha1(f"{kind}:{pk}".encode()).digest()
    return int.from_bytes(h[:8], "big") & ((1 << 63) - 1)


def ensure_collections(qdrant: QdrantClient) -> None:
    existing = {c.name for c in qdrant.get_collections().collections}
    for name in (COLL_LINES, COLL_CHUNKS):
        if name not in existing:
            qdrant.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
            )
            log(f"colección creada: {name}", "ok")


def embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def context_for_song(song: Song) -> dict:
    """Payload común a todos los puntos de una canción."""
    album = song.album
    artist = album.artist
    return {
        "song_id": song.id,
        "song_title": song.title,
        "song_slug": song.slug,
        "album_slug": album.slug,
        "album_title": album.title,
        "artist_slug": artist.slug,
        "year": album.year,
    }


def embed_lines(openai: OpenAI, qdrant: QdrantClient, batch_size: int) -> int:
    total = 0
    with get_session() as db:
        # Cargamos todas las lines en memoria — son ~5K, sobra
        rows = (
            db.query(Line)
            .join(Song, Line.song_id == Song.id)
            .join(Album, Song.album_id == Album.id)
            .join(Artist, Album.artist_id == Artist.id)
            .all()
        )
        log(f"lines en BD: {len(rows)}")

        # Cache de song context
        song_ctx: dict[int, dict] = {}

        batch_texts: list[str] = []
        batch_meta: list[Line] = []

        def flush() -> None:
            nonlocal total, batch_texts, batch_meta
            if not batch_texts:
                return
            vectors = embed_batch(openai, batch_texts)
            points = []
            for line, vec in zip(batch_meta, vectors, strict=True):
                if line.song_id not in song_ctx:
                    song_ctx[line.song_id] = context_for_song(line.song)
                payload = {
                    **song_ctx[line.song_id],
                    "line_index": line.line_index,
                    "stanza_index": line.stanza_index,
                    "text": line.text,
                }
                points.append(
                    PointStruct(id=stable_id("line", line.id), vector=vec, payload=payload)
                )
            qdrant.upsert(collection_name=COLL_LINES, points=points)
            total += len(points)
            batch_texts = []
            batch_meta = []

        for line in rows:
            batch_texts.append(line.text)
            batch_meta.append(line)
            if len(batch_texts) >= batch_size:
                flush()
                log(f"  ... {total} líneas embedidas")
        flush()
    return total


def embed_chunks(openai: OpenAI, qdrant: QdrantClient, batch_size: int) -> int:
    total = 0
    with get_session() as db:
        rows = (
            db.query(Chunk)
            .join(Song, Chunk.song_id == Song.id)
            .join(Album, Song.album_id == Album.id)
            .join(Artist, Album.artist_id == Artist.id)
            .all()
        )
        log(f"chunks en BD: {len(rows)}")

        song_ctx: dict[int, dict] = {}
        batch_texts: list[str] = []
        batch_meta: list[Chunk] = []

        def flush() -> None:
            nonlocal total, batch_texts, batch_meta
            if not batch_texts:
                return
            vectors = embed_batch(openai, batch_texts)
            points = []
            for chunk, vec in zip(batch_meta, vectors, strict=True):
                if chunk.song_id not in song_ctx:
                    song_ctx[chunk.song_id] = context_for_song(chunk.song)
                payload = {
                    **song_ctx[chunk.song_id],
                    "start_line_index": chunk.start_line_index,
                    "end_line_index": chunk.end_line_index,
                    "text": chunk.text,
                }
                points.append(
                    PointStruct(id=stable_id("chunk", chunk.id), vector=vec, payload=payload)
                )
            qdrant.upsert(collection_name=COLL_CHUNKS, points=points)
            total += len(points)
            batch_texts = []
            batch_meta = []

        for chunk in rows:
            batch_texts.append(chunk.text)
            batch_meta.append(chunk)
            if len(batch_texts) >= batch_size:
                flush()
                log(f"  ... {total} chunks embedidos")
        flush()
    return total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["lines", "chunks"], help="Solo embed uno de los dos")
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args()

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return

    openai = OpenAI(api_key=settings.openai_api_key)
    qdrant = QdrantClient(url=settings.qdrant_url)
    ensure_collections(qdrant)

    if args.only != "chunks":
        n_lines = embed_lines(openai, qdrant, args.batch_size)
        log(f"lines embedidas: {n_lines}", "ok")
    if args.only != "lines":
        n_chunks = embed_chunks(openai, qdrant, args.batch_size)
        log(f"chunks embedidos: {n_chunks}", "ok")


if __name__ == "__main__":
    main()
