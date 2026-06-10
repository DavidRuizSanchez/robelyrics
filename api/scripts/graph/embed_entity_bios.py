"""Vectoriza las biografías enciclopédicas (bio_long de Person y Band) en la
colección Qdrant `entities_v1`, para cobertura máxima del corpus.

Cada entidad con `bio_long` se trocea e indexa con payload {entity_type,
entity_slug, label}. Idempotente (id determinista por entidad+chunk).

Uso: python -m scripts.graph.embed_entity_bios [--dry-run]
"""
from __future__ import annotations

import argparse
import uuid
from typing import Any

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from app.config import get_settings
from app.db.models import Band, Person
from scripts.research.common import get_session, log
from scripts.research.embed_interpretations import chunk_text, embed_batch

EMBED_DIM = 3072
COLLECTION = "entities_v1"


def _point_id(entity_type: str, entity_id: int, chunk_index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"bio:{entity_type}:{entity_id}:{chunk_index}"))


def ensure_collection(qdrant: QdrantClient) -> None:
    if COLLECTION not in {c.name for c in qdrant.get_collections().collections}:
        qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        log(f"colección Qdrant creada: {COLLECTION}", "ok")


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

    pending: list[dict[str, Any]] = []
    with get_session() as db:
        rows: list[tuple[str, Any]] = (
            [("person", p) for p in db.query(Person).filter(Person.bio_long.isnot(None)).all()]
            + [("band", b) for b in db.query(Band).filter(Band.bio_long.isnot(None)).all()]
        )
        for etype, e in rows:
            text = (e.bio_long or "").strip()
            if len(text) < 200:
                continue
            label = getattr(e, "stage_name", None) or getattr(e, "full_name", None) or getattr(e, "name", "")
            for idx, ch in enumerate(chunk_text(text)):
                pending.append({
                    "text": ch, "chunk_index": idx,
                    "entity_type": etype, "entity_id": e.id,
                    "entity_slug": e.slug, "label": label,
                })

    log(f"{len(pending)} chunks de bio a embedear")
    if args.dry_run or not pending:
        return

    batch_texts: list[str] = []
    batch_meta: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal batch_texts, batch_meta
        if not batch_texts:
            return
        vectors = embed_batch(openai, batch_texts)
        points = [
            PointStruct(
                id=_point_id(m["entity_type"], m["entity_id"], m["chunk_index"]),
                vector=vec,
                payload={
                    "entity_type": m["entity_type"], "entity_id": m["entity_id"],
                    "entity_slug": m["entity_slug"], "label": m["label"],
                    "chunk_index": m["chunk_index"], "fragmento": m["text"],
                },
            )
            for m, vec in zip(batch_meta, vectors, strict=True)
        ]
        qdrant.upsert(collection_name=COLLECTION, points=points)
        batch_texts, batch_meta = [], []

    for entry in pending:
        batch_texts.append(entry["text"])
        batch_meta.append(entry)
        if len(batch_texts) >= args.batch_size:
            flush()
    flush()
    log(f"upsert completado: {len(pending)} chunks en {COLLECTION}", "ok")


if __name__ == "__main__":
    main()
