"""Hybrid retrieval: vector (Qdrant) + BM25 (Postgres FTS) + Reciprocal Rank Fusion."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from qdrant_client.http.models import FieldCondition, Filter, MatchValue, Range
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.qdrant_client import get_qdrant

LINES_COLLECTION = "lines_v1"
CHUNKS_COLLECTION = "chunks_v1"
INTERPRETATIONS_COLLECTION = "interpretations_v1"

# Boost factor aplicado al score RRF de un hit cuando su song_id aparece
# en las fuentes fan vectorialmente cercanas a la query. Promociona
# canciones cuyo CONTEXTO FAN (no sus letras aisladas) casa con la query.
INTERPRETATION_BOOST = 1.6


@dataclass
class Hit:
    """Resultado normalizado del retrieval, antes de rerank."""
    line_id: int | None
    song_id: int
    line_index: int | None  # solo si la fuente es una línea
    text: str
    score: float
    source: str  # "vector_lines" | "vector_chunks" | "bm25"
    payload: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Filtros
# --------------------------------------------------------------------------- #
def build_qdrant_filter(
    artist: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> Filter | None:
    must: list[FieldCondition] = []
    if artist:
        must.append(FieldCondition(key="artist_slug", match=MatchValue(value=artist)))
    if year_from is not None or year_to is not None:
        must.append(
            FieldCondition(
                key="year",
                range=Range(gte=year_from, lte=year_to),
            )
        )
    if not must:
        return None
    return Filter(must=must)


# --------------------------------------------------------------------------- #
# Vector search
# --------------------------------------------------------------------------- #
def vector_search(
    collection: str,
    query_vec: list[float],
    k: int = 20,
    filters: Filter | None = None,
) -> list[Hit]:
    qdrant = get_qdrant()
    # qdrant-client 1.17+: search() eliminado, usar query_points()
    resp = qdrant.query_points(
        collection_name=collection,
        query=query_vec,
        limit=k,
        query_filter=filters,
    )
    out: list[Hit] = []
    for r in resp.points:
        p = r.payload or {}
        out.append(
            Hit(
                line_id=None,  # qdrant point ids no son line.id (son hash); se reata después
                song_id=int(p.get("song_id", 0)),
                line_index=p.get("line_index"),
                text=p.get("text", ""),
                score=float(r.score),
                source="vector_lines" if collection == LINES_COLLECTION else "vector_chunks",
                payload=p,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# BM25 (Postgres FTS sobre lines.text con config es_unaccent)
# --------------------------------------------------------------------------- #
def bm25_search(
    db: Session,
    query: str,
    k: int = 20,
    artist: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> list[Hit]:
    """BM25 sobre lines.text_tsv con config es_unaccent."""
    # Cast explícito de los parámetros nullable: psycopg3 no puede inferir
    # el tipo cuando el primer uso es IS NULL.
    sql = """
        SELECT l.id AS line_id, l.song_id, l.line_index, l.text,
               ts_rank_cd(l.text_tsv, q) AS rank,
               s.title AS song_title, s.slug AS song_slug,
               al.title AS album_title, al.slug AS album_slug, al.year,
               a.slug AS artist_slug, a.name AS artist_name
        FROM lines l
        JOIN songs s ON s.id = l.song_id
        JOIN albums al ON al.id = s.album_id
        JOIN artists a ON a.id = al.artist_id,
             websearch_to_tsquery('es_unaccent', :q) AS q
        WHERE l.text_tsv @@ q
          AND (CAST(:artist AS TEXT) IS NULL OR a.slug = CAST(:artist AS TEXT))
          AND (CAST(:yfrom AS INTEGER) IS NULL OR al.year >= CAST(:yfrom AS INTEGER))
          AND (CAST(:yto AS INTEGER) IS NULL OR al.year <= CAST(:yto AS INTEGER))
        ORDER BY rank DESC
        LIMIT :k
    """
    rows = db.execute(
        text(sql),
        {"q": query, "k": k, "artist": artist, "yfrom": year_from, "yto": year_to},
    ).mappings().all()
    out: list[Hit] = []
    for r in rows:
        out.append(
            Hit(
                line_id=int(r["line_id"]),
                song_id=int(r["song_id"]),
                line_index=int(r["line_index"]),
                text=r["text"],
                score=float(r["rank"]),
                source="bm25",
                payload={
                    "song_title": r["song_title"],
                    "song_slug": r["song_slug"],
                    "album_title": r["album_title"],
                    "album_slug": r["album_slug"],
                    "year": r["year"],
                    "artist_slug": r["artist_slug"],
                    "artist_name": r["artist_name"],
                },
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Reciprocal Rank Fusion
# --------------------------------------------------------------------------- #
def search_interpretations_for_song_ids(
    query_vec: list[float], k: int = 10, score_threshold: float = 0.35
) -> dict[int, float]:
    """Busca en interpretations_v1 fuentes semánticamente cercanas a la query.
    Devuelve {song_id: best_score} extrayendo `payload.song_ids` (lista de ints).

    Útil cuando la query usa metáforas que las letras NO contienen literalmente,
    pero los fans han documentado el simbolismo (ej: "primavera = lo bonito").
    """
    qdrant = get_qdrant()
    try:
        resp = qdrant.query_points(
            collection_name=INTERPRETATIONS_COLLECTION,
            query=query_vec,
            limit=k,
            score_threshold=score_threshold,
        )
    except Exception:  # noqa: BLE001
        return {}
    out: dict[int, float] = {}
    for h in resp.points:
        for sid in (h.payload or {}).get("song_ids") or []:
            try:
                sid_int = int(sid)
            except (TypeError, ValueError):
                continue
            out[sid_int] = max(out.get(sid_int, 0.0), float(h.score))
    return out


def rrf_fuse(
    *ranked_lists: list[Hit],
    k: int = 60,
    top_n: int = 10,
    boost_song_ids: dict[int, float] | None = None,
) -> list[Hit]:
    """Combina varias listas ordenadas por rank usando RRF.

    Score RRF = sum(1 / (k + rank_i)) sobre todas las listas donde aparece.

    Clave de identidad de un Hit: (song_id, line_index) si es una línea, sino (song_id, text).
    Si una clave aparece en varias listas, su score se suma.
    """
    scores: dict[tuple, float] = {}
    representative: dict[tuple, Hit] = {}
    for ranked in ranked_lists:
        for rank, hit in enumerate(ranked, start=1):
            if hit.line_index is not None:
                key = (hit.song_id, hit.line_index)
            else:
                key = (hit.song_id, hit.text[:200])
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            # Quedamos con el primer hit como representativo (pero el score sumado)
            if key not in representative:
                representative[key] = hit
    # Aplicar boost a canciones cuyo song_id casa con interpretations_v1
    if boost_song_ids:
        for key in list(scores.keys()):
            song_id = key[0]
            if song_id in boost_song_ids:
                # Multiplica el score por el boost (más alto = sube más en el ranking)
                scores[key] *= INTERPRETATION_BOOST

    # Reordenar
    fused = sorted(representative.values(), key=lambda h: -scores[
        (h.song_id, h.line_index) if h.line_index is not None else (h.song_id, h.text[:200])
    ])
    # Asignar score combinado al hit
    for h in fused:
        key = (h.song_id, h.line_index) if h.line_index is not None else (h.song_id, h.text[:200])
        h.score = scores[key]
    return fused[:top_n]
