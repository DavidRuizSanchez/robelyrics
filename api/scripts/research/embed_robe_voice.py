"""Embeds + indexa el corpus de VOZ DE ROBE en Qdrant `robe_voice_v1`.

Alimenta el consultorio "Pregúntale al viento". Indexa los InterpretationSource
cuyo `kind` pertenece al corpus de voz:
  - robe_quote     → cita literal de Robe (author_is_robe=true)
  - robe_prose     → prosa suya (novela/agradecimientos) (author_is_robe=true)
  - robe_interview → transcripción de entrevista donde HABLA Robe (true)
  - about_robe     → homenaje/análisis de terceros sobre Robe (author_is_robe=FALSE):
                     vale como contexto, NUNCA como cita en su voz.

El payload lleva `author_is_robe` para que el retrieval del consultorio filtre
el núcleo (lo que dijo Robe) frente al contexto de terceros.

Idempotente: id determinista por (source_id, chunk_index).

Ejecución: docker compose exec api python -m scripts.research.embed_robe_voice
"""
from __future__ import annotations

import argparse
from typing import Any

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from app.config import get_settings
from app.db.models import InterpretationSource
from scripts.research.common import get_session, log
from scripts.research.embed_interpretations import (
    chunk_text,
    embed_batch,
    stable_point_id,
)

EMBED_DIM = 3072
COLLECTION = "robe_voice_v1"

# kinds que componen el corpus de voz. author_is_robe = kind != "about_robe".
VOICE_KINDS = ("robe_quote", "robe_prose", "robe_interview", "about_robe")
# Las citas son cortas y autocontenidas: 1 chunk, sin trocear.
SINGLE_CHUNK_KINDS = {"robe_quote"}


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
    n_sources = 0
    with get_session() as db:
        sources = (
            db.query(InterpretationSource)
            .filter(
                InterpretationSource.kind.in_(VOICE_KINDS),
                InterpretationSource.content_clean.isnot(None),
            )
            .all()
        )
        log(f"{len(sources)} fuentes de voz Robe")
        for src in sources:
            text = src.content_clean or ""
            chunks = [text] if src.kind in SINGLE_CHUNK_KINDS else chunk_text(text)
            base = {
                "source_id": src.id,
                "tipo": src.kind,
                "titulo": src.title,
                "url": src.url,
                "fecha": src.published_at.isoformat() if src.published_at else None,
                "author_is_robe": src.kind != "about_robe",
            }
            for idx, ch in enumerate(chunks):
                pending.append({"text": ch, "chunk_index": idx, **base})
            n_sources += 1

    log(f"{len(pending)} chunks a embedear")
    if args.dry_run:
        log("DRY-RUN: no se sube nada", "warn")
        return

    batch_texts: list[str] = []
    batch_meta: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal batch_texts, batch_meta
        if not batch_texts:
            return
        vectors = embed_batch(openai, batch_texts)
        points = []
        for meta, vec in zip(batch_meta, vectors, strict=True):
            points.append(
                PointStruct(
                    id=stable_point_id(meta["source_id"], meta["chunk_index"]),
                    vector=vec,
                    payload={
                        "source_id": meta["source_id"],
                        "tipo": meta["tipo"],
                        "titulo": meta["titulo"],
                        "url": meta["url"],
                        "fecha": meta["fecha"],
                        "author_is_robe": meta["author_is_robe"],
                        "chunk_index": meta["chunk_index"],
                        "fragmento": meta["text"],
                    },
                )
            )
        qdrant.upsert(collection_name=COLLECTION, points=points)
        batch_texts = []
        batch_meta = []

    for entry in pending:
        batch_texts.append(entry["text"])
        batch_meta.append(entry)
        if len(batch_texts) >= args.batch_size:
            flush()
    flush()

    log(f"upsert completado: {len(pending)} chunks de {n_sources} fuentes en {COLLECTION}", "ok")


if __name__ == "__main__":
    main()
