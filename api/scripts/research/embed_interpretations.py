"""Embeds + indexa pasajes de fan-content en Qdrant `interpretations_v1`.

Para cada InterpretationSource con content_clean:
  1. Trocea el texto en chunks de ~200-400 tokens (usando aproximación
     palabras: ~1 token = 0.75 palabras → 250 palabras ≈ 333 tokens).
  2. Cada chunk se embedde con OpenAI text-embedding-3-large (3072 dim).
  3. Upsert a Qdrant con payload: source_id, kind, url, author, title.

Idempotencia: el id en Qdrant se deriva de hash(source_id, chunk_index)
para que re-correr no duplique.

⚠️ REQUIERE Fase 1 + distill.py SI quieres que las interpretaciones se
   linken a song_ids. Este script puede correr antes y rellena el
   campo `song_ids` solo si InterpretationSource.referenced_song_ids
   ya está poblado.

Ejecución: docker compose exec api python -m scripts.research.embed_interpretations
"""
from __future__ import annotations

import argparse
import hashlib
from typing import Any

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FilterSelector,
    PointStruct,
    VectorParams,
)

from app.config import get_settings
from app.db.models import InterpretationSource
from scripts.research.common import get_session, log

EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 3072
COLLECTION = "interpretations_v1"
CHUNK_WORDS = 250  # ~330 tokens
CHUNK_OVERLAP_WORDS = 40


def chunk_text(text: str, words_per_chunk: int = CHUNK_WORDS, overlap: int = CHUNK_OVERLAP_WORDS) -> list[str]:
    words = text.split()
    if len(words) <= words_per_chunk:
        return [text]
    chunks: list[str] = []
    step = words_per_chunk - overlap
    for i in range(0, len(words), step):
        chunk = " ".join(words[i : i + words_per_chunk])
        if chunk:
            chunks.append(chunk)
        if i + words_per_chunk >= len(words):
            break
    return chunks


def stable_point_id(source_id: int, chunk_index: int) -> int:
    """Genera un id determinista de 64 bits para Qdrant a partir de
    (source_id, chunk_index). Permite re-correr sin duplicar."""
    h = hashlib.sha1(f"{source_id}:{chunk_index}".encode()).digest()
    return int.from_bytes(h[:8], "big") & ((1 << 63) - 1)  # 63 bits para que sea positive


def ensure_collection(qdrant: QdrantClient) -> None:
    existing = {c.name for c in qdrant.get_collections().collections}
    if COLLECTION not in existing:
        qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        log(f"colección Qdrant creada: {COLLECTION}", "ok")
    else:
        log(f"colección {COLLECTION} ya existe")


def embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return

    openai = OpenAI(api_key=settings.openai_api_key)
    qdrant = QdrantClient(url=settings.qdrant_url)
    ensure_collection(qdrant)

    # Materializamos a dicts plain DENTRO de la sesión para no depender
    # de los objetos ORM una vez cerrada (DetachedInstanceError).
    pending_chunks: list[dict[str, Any]] = []
    total_sources = 0

    with get_session() as db:
        sources = db.query(InterpretationSource).filter(InterpretationSource.content_clean.isnot(None)).all()
        log(f"{len(sources)} fuentes con contenido")

        for src in sources:
            chunks = chunk_text(src.content_clean or "")
            base_payload = {
                "source_id": src.id,
                "kind": src.kind,
                "url": src.url,
                "title": src.title,
                "author": src.author,
                "song_ids": src.referenced_song_ids or [],
                "quality_score": src.quality_score,
            }
            for idx, ch in enumerate(chunks):
                pending_chunks.append({"text": ch, "chunk_index": idx, **base_payload})
            total_sources += 1

    log(f"{len(pending_chunks)} chunks a embedear")

    if args.dry_run:
        log("DRY-RUN: no se embedará ni subirá a Qdrant", "warn")
        return

    batch_texts: list[str] = []
    batch_meta: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal batch_texts, batch_meta
        if not batch_texts:
            return
        vectors = embed_batch(openai, batch_texts)
        batch_points = []
        for meta, vec in zip(batch_meta, vectors, strict=True):
            batch_points.append(
                PointStruct(
                    id=stable_point_id(meta["source_id"], meta["chunk_index"]),
                    vector=vec,
                    payload={k: v for k, v in meta.items() if k != "text"},
                )
            )
        qdrant.upsert(collection_name=COLLECTION, points=batch_points)
        batch_texts = []
        batch_meta = []

    for entry in pending_chunks:
        batch_texts.append(entry["text"])
        batch_meta.append(entry)
        if len(batch_texts) >= args.batch_size:
            flush()
            log(f"  ... {len(batch_meta)} batch flushed (acum sigue)")
    flush()

    log(f"upsert completado: {len(pending_chunks)} chunks de {total_sources} fuentes", "ok")


if __name__ == "__main__":
    main()
