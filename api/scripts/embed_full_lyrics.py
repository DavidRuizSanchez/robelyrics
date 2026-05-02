"""Vectoriza la letra COMPLETA de cada canción a Qdrant `lyrics_full_v1`.

Por qué: el retrieval por líneas o chunks falla cuando la query es conceptual
de alto nivel (ej. "adentrarse en territorios emocionales desconocidos") y
la canción dice eso a través de varias estrofas pero ningún chunk individual
lo refleja claramente. Vectorizar la letra entera captura el "tema general".

Cada canción es un único punto Qdrant con:
  - id determinista por song_id
  - payload: {song_id, song_title, song_slug, artist_slug, album_slug, year}
  - vector: embedding de `lyrics_clean` (truncado a ~3000 tokens si hace falta)

Idempotente. ~$0.001 total para 144 canciones.

Ejecución:
  docker compose exec api python -m scripts.embed_full_lyrics
"""
from __future__ import annotations

import argparse
import hashlib

from openai import OpenAI
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from app.config import get_settings
from app.db.models import Song
from app.services.qdrant_client import get_qdrant
from scripts.research.common import get_session, log

EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 3072
COLLECTION = "lyrics_full_v1"
MAX_CHARS = 12_000  # ~3K tokens, sobra para 99% de canciones


def stable_id(song_id: int) -> int:
    h = hashlib.sha1(f"full:{song_id}".encode()).digest()
    return int.from_bytes(h[:8], "big") & ((1 << 63) - 1)


def ensure_collection(qdrant) -> None:
    existing = {c.name for c in qdrant.get_collections().collections}
    if COLLECTION not in existing:
        qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        log(f"colección creada: {COLLECTION}", "ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return

    openai = OpenAI(api_key=settings.openai_api_key)
    qdrant = get_qdrant()
    ensure_collection(qdrant)

    # Materializar a dicts (evita DetachedInstance)
    with get_session() as db:
        items = []
        for s in db.query(Song).filter(Song.lyrics_clean.isnot(None)).all():
            text = (s.lyrics_clean or "").strip()
            if len(text) < 30:
                continue
            items.append({
                "song_id": s.id,
                "song_title": s.title,
                "song_slug": s.slug,
                "artist_slug": s.album.artist.slug,
                "album_slug": s.album.slug,
                "year": s.album.year,
                "text": text[:MAX_CHARS],
            })

    log(f"canciones a vectorizar: {len(items)}")
    if not items:
        return

    n_uploaded = 0
    for i in range(0, len(items), args.batch_size):
        batch = items[i : i + args.batch_size]
        texts = [it["text"] for it in batch]
        vectors = [d.embedding for d in openai.embeddings.create(model=EMBED_MODEL, input=texts).data]
        points = []
        for it, vec in zip(batch, vectors, strict=True):
            payload = {k: v for k, v in it.items() if k != "text"}
            payload["song_ids"] = [it["song_id"]]  # mismo formato que interpretations_v1
            payload["kind"] = "lyrics_full"
            points.append(PointStruct(id=stable_id(it["song_id"]), vector=vec, payload=payload))
        qdrant.upsert(collection_name=COLLECTION, points=points)
        n_uploaded += len(points)
        log(f"  ... {n_uploaded} canciones subidas")

    log(f"upsert completado: {n_uploaded} en {COLLECTION}", "ok")


if __name__ == "__main__":
    main()
