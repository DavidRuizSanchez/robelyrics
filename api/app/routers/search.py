"""Search endpoints: /search/semantic y /search/complete."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import Line, User
from app.db.session import get_db
from app.services.auth import get_current_user
from app.services.embeddings import get_embedder
from app.services.reranker import rerank
from app.services.retrieval import (
    CHUNKS_COLLECTION,
    LINES_COLLECTION,
    Hit,
    bm25_search,
    build_qdrant_filter,
    rrf_fuse,
    search_interpretations_for_song_ids,
    vector_search,
)

router = APIRouter(prefix="/search", tags=["search"])


# --------------------------------------------------------------------------- #
# /search/semantic
# --------------------------------------------------------------------------- #
class SemanticIn(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    artist: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    k: int = Field(5, ge=1, le=10)


class SemanticHit(BaseModel):
    line_text: str
    song: dict[str, Any]
    album: dict[str, Any]
    artist: dict[str, Any]
    line_index: int | None
    context_before: list[str]
    context_after: list[str]
    fan_context: str | None
    fan_context_sources: list[dict[str, Any]]
    why: str


class SemanticOut(BaseModel):
    query: str
    results: list[SemanticHit]


@router.post("/semantic", response_model=SemanticOut)
def semantic(
    body: SemanticIn,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> SemanticOut:
    embedder = get_embedder()
    query_vec = embedder.embed_one(body.query)
    qfilter = build_qdrant_filter(
        artist=body.artist,
        year_from=body.year_from,
        year_to=body.year_to,
    )

    # Retrieval híbrido (top-K más generoso → más material para el reranker)
    lines_hits = vector_search(LINES_COLLECTION, query_vec, k=40, filters=qfilter)
    chunks_hits = vector_search(CHUNKS_COLLECTION, query_vec, k=30, filters=qfilter)
    bm25_hits = bm25_search(
        db,
        body.query,
        k=20,
        artist=body.artist,
        year_from=body.year_from,
        year_to=body.year_to,
    )

    # Canal extra: fan-content semánticamente cercano a la query → song_ids con boost.
    # Captura metáforas que las letras NO contienen pero los fans han documentado.
    boost_ids = search_interpretations_for_song_ids(query_vec, k=10)

    fused = rrf_fuse(
        lines_hits, chunks_hits, bm25_hits,
        top_n=20,
        boost_song_ids=boost_ids,
    )
    fused = _hydrate_line_ids(db, fused)

    reranked = rerank(body.query, fused, db, top_k=body.k)

    return SemanticOut(
        query=body.query,
        results=[
            SemanticHit(
                line_text=r.line_text,
                song=r.song,
                album=r.album,
                artist=r.artist,
                line_index=r.line_index,
                context_before=r.context_before,
                context_after=r.context_after,
                fan_context=r.fan_context,
                fan_context_sources=r.fan_context_sources,
                why=r.why,
            )
            for r in reranked
        ],
    )


def _hydrate_line_ids(db: Session, hits: list[Hit]) -> list[Hit]:
    """Resolve line_id from (song_id, line_index) for vector-source hits."""
    pairs = [(h.song_id, h.line_index) for h in hits if h.line_id is None and h.line_index is not None]
    if not pairs:
        return hits
    # Single query con OR
    from sqlalchemy import and_, or_
    cond = or_(*[and_(Line.song_id == sid, Line.line_index == idx) for sid, idx in pairs])
    rows = db.query(Line).filter(cond).all()
    by_key = {(l.song_id, l.line_index): l.id for l in rows}
    for h in hits:
        if h.line_id is None and h.line_index is not None:
            h.line_id = by_key.get((h.song_id, h.line_index))
    return hits


# --------------------------------------------------------------------------- #
# /search/complete
# --------------------------------------------------------------------------- #
class CompleteIn(BaseModel):
    query: str = Field(..., min_length=2, max_length=200)
    k: int = Field(3, ge=1, le=10)
    n_continuation: int = Field(3, ge=1, le=10)


class CompleteHit(BaseModel):
    matched_line: str
    continuation_lines: list[str]
    song: dict[str, Any]
    album: dict[str, Any]
    artist: dict[str, Any]


class CompleteOut(BaseModel):
    query: str
    results: list[CompleteHit]


@router.post("/complete", response_model=CompleteOut)
def complete(
    body: CompleteIn,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> CompleteOut:
    """Modo 'completar frase'. Prefiere matching léxico (BM25 con phraseto + pg_trgm fallback)."""
    matches = _phrase_search(db, body.query, k=body.k)
    if not matches:
        # Fallback: BM25 normal
        bm = bm25_search(db, body.query, k=body.k)
        matches = [(b.line_id, b.song_id, b.line_index, b.text, b.payload) for b in bm if b.line_id]
    if not matches:
        return CompleteOut(query=body.query, results=[])

    # Pre-fetch líneas siguientes
    out: list[CompleteHit] = []
    for line_id, song_id, line_index, matched_text, meta in matches:
        cont = (
            db.query(Line)
            .filter(Line.song_id == song_id, Line.line_index > line_index)
            .order_by(Line.line_index)
            .limit(body.n_continuation)
            .all()
        )
        out.append(
            CompleteHit(
                matched_line=matched_text,
                continuation_lines=[l.text for l in cont],
                song={"id": song_id, "title": meta.get("song_title", ""), "slug": meta.get("song_slug", "")},
                album={
                    "title": meta.get("album_title", ""),
                    "slug": meta.get("album_slug", ""),
                    "year": meta.get("year"),
                },
                artist={"slug": meta.get("artist_slug", ""), "name": meta.get("artist_name", "")},
            )
        )
    return CompleteOut(query=body.query, results=out)


def _phrase_search(db: Session, query: str, k: int) -> list[tuple[int, int, int, str, dict[str, Any]]]:
    """Busca frase con phraseto_tsquery (estricto orden) + pg_trgm como fallback fuzzy."""
    sql = """
        WITH q AS (
          SELECT phraseto_tsquery('es_unaccent', :q) AS phrase_q,
                 :q AS raw
        )
        SELECT l.id AS line_id, l.song_id, l.line_index, l.text,
               s.title AS song_title, s.slug AS song_slug,
               al.title AS album_title, al.slug AS album_slug, al.year,
               a.slug AS artist_slug, a.name AS artist_name,
               -- Score combinado: rank tsquery + similarity trgm
               (CASE WHEN l.text_tsv @@ (SELECT phrase_q FROM q)
                     THEN ts_rank_cd(l.text_tsv, (SELECT phrase_q FROM q)) ELSE 0 END
                + similarity(l.text, :q) * 0.5) AS score
        FROM lines l
        JOIN songs s ON s.id = l.song_id
        JOIN albums al ON al.id = s.album_id
        JOIN artists a ON a.id = al.artist_id
        WHERE l.text_tsv @@ (SELECT phrase_q FROM q)
           OR similarity(l.text, :q) > 0.3
        ORDER BY score DESC
        LIMIT :k
    """
    rows = db.execute(text(sql), {"q": query, "k": k}).mappings().all()
    out = []
    for r in rows:
        out.append((
            int(r["line_id"]),
            int(r["song_id"]),
            int(r["line_index"]),
            r["text"],
            {
                "song_title": r["song_title"],
                "song_slug": r["song_slug"],
                "album_title": r["album_title"],
                "album_slug": r["album_slug"],
                "year": r["year"],
                "artist_slug": r["artist_slug"],
                "artist_name": r["artist_name"],
            },
        ))
    return out
