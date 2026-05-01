"""Vectoriza los `fan_consensus` destilados → Qdrant `interpretations_v1`.

Después del distill tenemos en `song_interpretations.payload.fan_consensus`
un resumen de 200-400 palabras por canción que SÍ explica explícitamente
las metáforas (ej: "los fans interpretan la primavera como una metáfora
del bien efímero que se acaba"). Vectorizar esos resúmenes mejora el
retrieval semántico de queries metafóricas:
  - "se acabó lo bonito" pega vectorialmente con "primavera como bien
    efímero que se acaba" → song_id de Papel secante → boost en RRF.

Cada fan_consensus se sube como un punto Qdrant con:
  - id determinista (kind="consensus", song_id) → idempotente
  - payload.kind = "fan_consensus"
  - payload.song_ids = [song_id]   (para el boost del canal interpretations)
  - payload.confidence = high|medium|low

Ejecución:
  docker compose exec api python -m scripts.research.vectorize_consensus
"""
from __future__ import annotations

import argparse
import hashlib

from openai import OpenAI
from qdrant_client.http.models import PointStruct

from app.config import get_settings
from app.db.models import Song, SongInterpretation
from app.services.qdrant_client import get_qdrant
from scripts.research.common import get_session, log

EMBED_MODEL = "text-embedding-3-large"
COLLECTION = "interpretations_v1"


def stable_id(song_id: int) -> int:
    """Determinista para que re-ejecutar no duplique."""
    h = hashlib.sha1(f"consensus:{song_id}".encode()).digest()
    return int.from_bytes(h[:8], "big") & ((1 << 63) - 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--min-confidence", choices=["low", "medium", "high"], default="low",
                        help="Solo vectorizar consensus con confidence >= éste")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return
    openai = OpenAI(api_key=settings.openai_api_key)
    qdrant = get_qdrant()

    confidence_order = {"low": 0, "medium": 1, "high": 2}
    min_level = confidence_order[args.min_confidence]

    with get_session() as db:
        rows = (
            db.query(SongInterpretation, Song)
            .join(Song, SongInterpretation.song_id == Song.id)
            .all()
        )
        log(f"interpretaciones en BD: {len(rows)}")

        items: list[tuple[int, str, str, dict]] = []
        for interp, song in rows:
            if confidence_order[interp.confidence] < min_level:
                continue
            consensus = (interp.payload or {}).get("fan_consensus")
            if not consensus or len(consensus) < 80:
                continue
            items.append((song.id, song.title, consensus, interp.confidence))
        log(f"candidatos a vectorizar: {len(items)}")

        if not items:
            log("nada que vectorizar", "warn")
            return

        # Embed por batches
        i = 0
        n_uploaded = 0
        while i < len(items):
            batch = items[i : i + args.batch_size]
            texts = [c[2] for c in batch]
            resp = openai.embeddings.create(model=EMBED_MODEL, input=texts)
            vectors = [d.embedding for d in resp.data]
            points = []
            for (song_id, title, consensus, confidence), vec in zip(batch, vectors, strict=True):
                points.append(
                    PointStruct(
                        id=stable_id(song_id),
                        vector=vec,
                        payload={
                            "source_id": -song_id,  # negativo para distinguir de InterpretationSource real
                            "kind": "fan_consensus",
                            "title": f"Consenso fan: {title}",
                            "song_ids": [song_id],
                            "confidence": confidence,
                            "quality_score": 0.95 if confidence == "high" else 0.7 if confidence == "medium" else 0.5,
                        },
                    )
                )
            qdrant.upsert(collection_name=COLLECTION, points=points)
            n_uploaded += len(points)
            log(f"  ... {n_uploaded} consensus subidos")
            i += args.batch_size

    log(f"upsert completado: {n_uploaded} consensus en {COLLECTION}", "ok")


if __name__ == "__main__":
    main()
