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
from qdrant_client.http.models import FieldCondition, Filter, MatchValue

from app.services.qdrant_client import get_qdrant
from app.services.retrieval import (
    CHUNKS_COLLECTION,
    LINES_COLLECTION,
    Hit,
    bm25_search,
    build_qdrant_filter,
    rrf_fuse,
    search_interpretations_for_song_ids,
    search_lyrics_full_for_song_ids,
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
    start_seconds: int | None = None
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

    # Canales extra que aportan boost al RRF + candidatos forzados:
    #  - interpretations_v1: fan-content (metáforas documentadas por fans)
    #  - lyrics_full_v1: letra completa (queries conceptuales de alto nivel
    #    donde la canción habla del tema pero ningún chunk aislado lo refleja)
    boost_interp = search_interpretations_for_song_ids(query_vec, k=15)
    boost_full = search_lyrics_full_for_song_ids(query_vec, k=15)
    boost_ids: dict[int, float] = dict(boost_interp)
    for sid, sc in boost_full.items():
        boost_ids[sid] = max(boost_ids.get(sid, 0.0), sc)

    fused = rrf_fuse(
        lines_hits, chunks_hits, bm25_hits,
        top_n=20,
        boost_song_ids=boost_ids,
    )
    fused = _hydrate_line_ids(db, fused)

    fused = _inject_full_lyrics_candidates(query_vec, boost_full, fused, max_inject=5)

    # Dedup canónico ANTES del rerank: colapsamos versiones (live, comp...) a
    # la versión studio más antigua, traduciendo song_id al preferred_id. El
    # reranker recibe un único candidato por canción → su top-K viene limpio
    # y muestra siempre la versión canónica.
    canon = _canonical_song_map(db, [h.song_id for h in fused])
    seen_preferred: set[int] = set()
    deduped_fused: list[Hit] = []
    for h in fused:
        pref = canon.get(h.song_id, {}).get("preferred_id", h.song_id)
        if pref in seen_preferred:
            continue
        seen_preferred.add(pref)
        # Si esta entrada NO era ya la canónica, sustituyo el song_id pero
        # marco que el timestamp/line_index original era de otra versión y
        # no aplica a la canónica (lo borramos).
        if pref != h.song_id:
            h.song_id = pref
            h.start_seconds = None
            h.line_index = None
            h.line_id = None
        deduped_fused.append(h)
    fused = deduped_fused

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
                start_seconds=r.start_seconds,
                context_before=r.context_before,
                context_after=r.context_after,
                fan_context=r.fan_context,
                fan_context_sources=r.fan_context_sources,
                why=r.why,
            )
            for r in reranked
        ],
    )


def _inject_full_lyrics_candidates(
    query_vec: list[float],
    boost_full: dict[int, float],
    fused: list[Hit],
    max_inject: int = 5,
) -> list[Hit]:
    """Para canciones top de lyrics_full_v1 NO cubiertas en `fused`, añade su
    mejor línea (vector search filtrado por song_id) al pool de candidatos.

    Esto rescata canciones donde el conjunto de la letra encaja con una query
    conceptual pero ningún chunk individual lo refleja con suficiente score
    para entrar al RRF. Crítico para queries abstractas / temáticas.
    """
    if not boost_full:
        return fused
    covered = {h.song_id for h in fused}
    candidates = sorted(boost_full.items(), key=lambda x: -x[1])
    qdrant = get_qdrant()
    n_injected = 0
    for song_id, _ in candidates:
        if n_injected >= max_inject:
            break
        if song_id in covered:
            continue
        # Mejor línea de esa canción para representarla
        try:
            resp = qdrant.query_points(
                collection_name=LINES_COLLECTION,
                query=query_vec,
                limit=1,
                query_filter=Filter(
                    must=[FieldCondition(key="song_id", match=MatchValue(value=song_id))]
                ),
            )
        except Exception:  # noqa: BLE001
            continue
        if not resp.points:
            continue
        h = resp.points[0]
        p = h.payload or {}
        fused.append(
            Hit(
                line_id=None,
                song_id=song_id,
                line_index=p.get("line_index"),
                text=p.get("text", ""),
                score=float(h.score) * 0.8,  # peso ligeramente menor que candidatos del RRF normal
                source="full_lyrics_inject",
                payload=p,
            )
        )
        n_injected += 1
    return fused


def _canonical_song_map(db: Session, song_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Para cada song_id, devuelve la versión PREFERIDA de esa canción.

    "Preferida" = misma canción base (mismo artista, mismo título sin
    paréntesis finales) eligiendo:
        1. studio sobre live/compilation
        2. menor año
        3. menor song_id (desempate determinista)

    Devuelve {input_song_id: {preferred_id, title, slug, youtube_id,
                               album_title, album_slug, year, kind,
                               artist_slug, artist_name, is_substitute}}
    """
    if not song_ids:
        return {}
    sql = """
        WITH canon AS (
          SELECT s.id AS sid, a.artist_id,
                 lower(regexp_replace(s.title, '\\s*\\([^)]+\\)\\s*$', '')) AS canon_title
          FROM songs s
          JOIN albums a ON a.id = s.album_id
          WHERE s.id = ANY(:ids)
        ),
        ranked AS (
          SELECT
            c.sid AS input_id,
            s.id AS preferred_id, s.title, s.slug, s.youtube_id,
            al.title AS album_title, al.slug AS album_slug, al.year, al.kind,
            a.slug AS artist_slug, a.name AS artist_name,
            ROW_NUMBER() OVER (
              PARTITION BY c.sid
              ORDER BY (al.kind = 'studio') DESC, al.year ASC, s.id ASC
            ) AS rn
          FROM canon c
          JOIN albums al ON al.artist_id = c.artist_id
          JOIN songs s ON s.album_id = al.id
            AND lower(regexp_replace(s.title, '\\s*\\([^)]+\\)\\s*$', '')) = c.canon_title
          JOIN artists a ON a.id = c.artist_id
        )
        SELECT * FROM ranked WHERE rn = 1
    """
    rows = db.execute(text(sql), {"ids": song_ids}).mappings().all()
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        out[int(r["input_id"])] = {
            "preferred_id": int(r["preferred_id"]),
            "title": r["title"],
            "slug": r["slug"],
            "youtube_id": r["youtube_id"],
            "album_title": r["album_title"],
            "album_slug": r["album_slug"],
            "year": r["year"],
            "kind": r["kind"],
            "artist_slug": r["artist_slug"],
            "artist_name": r["artist_name"],
            "is_substitute": int(r["preferred_id"]) != int(r["input_id"]),
        }
    return out


def _hydrate_line_ids(db: Session, hits: list[Hit]) -> list[Hit]:
    """Resolve line_id + start_seconds para todos los tipos de hit.

    - Hits de `lines_v1`, BM25, inyectados → ya traen `line_index`.
    - Hits de `chunks_v1` → traen `start_line_index` en el payload, lo
      promovemos a `line_index` para hidratar el `start_seconds` de la
      primera línea del chunk (que es donde queremos saltar en el video).
    """
    # 1. Para chunks, copiar start_line_index → line_index (si aún no tiene)
    for h in hits:
        if h.line_index is None:
            sli = (h.payload or {}).get("start_line_index")
            if sli is not None:
                h.line_index = int(sli)

    pairs = [(h.song_id, h.line_index) for h in hits if h.line_index is not None]
    if not pairs:
        return hits
    from sqlalchemy import and_, or_
    cond = or_(*[and_(Line.song_id == sid, Line.line_index == idx) for sid, idx in pairs])
    rows = db.query(Line).filter(cond).all()
    by_key = {(l.song_id, l.line_index): (l.id, l.start_seconds) for l in rows}
    for h in hits:
        if h.line_index is not None:
            res = by_key.get((h.song_id, h.line_index))
            if res:
                if h.line_id is None:
                    h.line_id = res[0]
                if h.start_seconds is None:
                    h.start_seconds = res[1]
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
    start_seconds: int | None = None
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
    # Pedimos más para tener material tras dedup canónico
    matches = _phrase_search(db, body.query, k=body.k * 3)
    if not matches:
        bm = bm25_search(db, body.query, k=body.k * 3)
        matches = [
            (
                b.line_id,
                b.song_id,
                b.line_index,
                b.text,
                {**b.payload, "song_youtube_id": None, "start_seconds": b.start_seconds},
            )
            for b in bm if b.line_id
        ]
    if not matches:
        return CompleteOut(query=body.query, results=[])

    # Dedup canónico: una sola versión por canción (studio más antigua)
    canon = _canonical_song_map(db, [m[1] for m in matches])
    seen_preferred: set[int] = set()
    deduped_matches = []
    for m in matches:
        song_id = m[1]
        pref_id = canon.get(song_id, {}).get("preferred_id", song_id)
        if pref_id in seen_preferred:
            continue
        seen_preferred.add(pref_id)
        deduped_matches.append(m)
        if len(deduped_matches) >= body.k:
            break

    out: list[CompleteHit] = []
    for line_id, song_id, line_index, matched_text, meta in deduped_matches:
        cont = (
            db.query(Line)
            .filter(Line.song_id == song_id, Line.line_index > line_index)
            .order_by(Line.line_index)
            .limit(body.n_continuation)
            .all()
        )
        # Sustituir metadata por la versión preferida si es duplicado live/comp
        c = canon.get(song_id)
        if c and c["is_substitute"]:
            song_meta = {
                "id": c["preferred_id"],
                "title": c["title"],
                "slug": c["slug"],
                "youtube_id": c["youtube_id"],
            }
            album_meta = {"title": c["album_title"], "slug": c["album_slug"], "year": c["year"]}
            artist_meta = {"slug": c["artist_slug"], "name": c["artist_name"]}
            start_seconds = None  # timestamp del live no aplica a studio
        else:
            song_meta = {
                "id": song_id,
                "title": meta.get("song_title", ""),
                "slug": meta.get("song_slug", ""),
                "youtube_id": meta.get("song_youtube_id"),
            }
            album_meta = {
                "title": meta.get("album_title", ""),
                "slug": meta.get("album_slug", ""),
                "year": meta.get("year"),
            }
            artist_meta = {"slug": meta.get("artist_slug", ""), "name": meta.get("artist_name", "")}
            start_seconds = meta.get("start_seconds")

        out.append(
            CompleteHit(
                matched_line=matched_text,
                continuation_lines=[l.text for l in cont],
                start_seconds=start_seconds,
                song=song_meta,
                album=album_meta,
                artist=artist_meta,
            )
        )
    return CompleteOut(query=body.query, results=out)


def _phrase_search(db: Session, query: str, k: int) -> list[tuple[int, int, int, str, dict[str, Any]]]:
    """Busca frase con phraseto_tsquery (estricto orden) + pg_trgm como fallback fuzzy.

    Scoring:
      - Si la frase completa hace match (phraseto_tsquery), recibe un boost masivo (+10).
        Eso garantiza que líneas que CONTIENEN literalmente la query del usuario
        ganan a líneas con un trozo similar pero corto.
      - similarity (pg_trgm) solo aporta cuando no hay phrase match.

    Dedup:
      - Una canción solo aparece UNA vez en el resultado (DISTINCT ON song_id).
        Si una canción tiene 5 estrofas con la misma línea, solo entra la mejor.
    """
    sql = """
        WITH q AS (
          SELECT phraseto_tsquery('es_unaccent', :q) AS phrase_q,
                 :q AS raw
        ),
        scored AS (
          SELECT l.id AS line_id, l.song_id, l.line_index, l.text, l.start_seconds,
                 s.title AS song_title, s.slug AS song_slug, s.youtube_id,
                 al.title AS album_title, al.slug AS album_slug, al.year,
                 a.slug AS artist_slug, a.name AS artist_name,
                 (l.text_tsv @@ (SELECT phrase_q FROM q)) AS has_phrase_match,
                 (CASE WHEN l.text_tsv @@ (SELECT phrase_q FROM q)
                       THEN 10.0 + ts_rank_cd(l.text_tsv, (SELECT phrase_q FROM q))
                       ELSE 0.0 END
                  + similarity(l.text, :q) * 0.3) AS score
          FROM lines l
          JOIN songs s ON s.id = l.song_id
          JOIN albums al ON al.id = s.album_id
          JOIN artists a ON a.id = al.artist_id
          WHERE l.text_tsv @@ (SELECT phrase_q FROM q)
             OR similarity(l.text, :q) > 0.3
        ),
        deduped AS (
          -- Una sola línea por canción. Entre las que matchean la frase
          -- preferimos la más temprana del audio (primera aparición).
          -- Si solo hay matches por similarity (sin phrase), priorizamos score.
          SELECT DISTINCT ON (song_id) *
          FROM scored
          ORDER BY song_id, has_phrase_match DESC, line_index ASC, score DESC
        )
        -- Entre canciones distintas: orden por score (canciones con phrase match arriba)
        SELECT * FROM deduped ORDER BY score DESC, line_index ASC LIMIT :k
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
                "song_youtube_id": r["youtube_id"],
                "album_title": r["album_title"],
                "album_slug": r["album_slug"],
                "year": r["year"],
                "artist_slug": r["artist_slug"],
                "artist_name": r["artist_name"],
                "start_seconds": r["start_seconds"],
            },
        ))
    return out
