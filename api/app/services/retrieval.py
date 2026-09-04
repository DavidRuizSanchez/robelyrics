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
LYRICS_FULL_COLLECTION = "lyrics_full_v1"
ROBE_VOICE_COLLECTION = "robe_voice_v1"


def search_robe_voice(
    query_vec: list[float], k: int = 4, score_threshold: float = 0.34
) -> list[dict[str, Any]]:
    """Busca en robe_voice_v1 lo que dijo Robe (entrevistas, citas, su prosa)
    relacionado con la query. Solo material de su propia voz (author_is_robe).
    Enriquece el buscador semántico: junto al verso, lo que Robe dijo del tema.
    """
    qdrant = get_qdrant()
    flt = Filter(must=[FieldCondition(key="author_is_robe", match=MatchValue(value=True))])
    try:
        resp = qdrant.query_points(
            collection_name=ROBE_VOICE_COLLECTION,
            query=query_vec,
            limit=k,
            query_filter=flt,
            score_threshold=score_threshold,
        )
    except Exception:  # noqa: BLE001
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in resp.points:
        p = r.payload or {}
        frag = (p.get("fragmento") or "").strip()
        titulo = p.get("titulo") or ""
        if not frag or titulo in seen:  # 1 pasaje por fuente
            continue
        seen.add(titulo)
        out.append(
            {
                "fragmento": frag[:400],
                "titulo": titulo or "Robe",
                "tipo": p.get("tipo") or "entrevista",
                "url": p.get("url"),
                "score": float(r.score),
            }
        )
    return out

def search_interpretations_passages(
    db: Session,
    query_vec: list[float],
    *,
    k: int = 8,
    score_threshold: float = 0.35,
    exclude_kinds: Iterable[str] = ("youtube_comment",),
    max_chars: int = 1200,
) -> list[dict[str, Any]]:
    """Pasajes de fan-content semánticamente cercanos a la query, CON su texto.

    `search_interpretations_for_song_ids` lee la misma colección pero solo devuelve
    `payload.song_ids` para boostear el ranking; si una fuente no está ligada a
    ninguna canción, su hit se descarta y el material no sale por ningún sitio.
    Medido en producción: 420 de las 731 fuentes del corpus estaban en ese caso
    —141 transcripciones de YouTube y las 110 anotaciones de Genius entre ellas—,
    vectorizadas pero irrecuperables. Esta función es su camino de salida: recupera
    por SIGNIFICADO y devuelve el pasaje, sin depender del enlace a canción.

    El texto no vive en Qdrant a propósito (`embed_interpretations` lo excluye del
    payload), pero sí guarda `chunk_index`, así que el pasaje se rehidrata gratis:
    se relee `content_clean` de la BD y se vuelve a trocear con el MISMO
    `chunk_text` que se usó al indexar. Si el contenido cambió después del embed y
    el índice queda fuera de rango, se cae al primer trozo — el re-embed nocturno
    (bloque de 03:30) realinea solo.
    """
    from app.db.models import InterpretationSource
    from scripts.research.embed_interpretations import chunk_text

    qdrant = get_qdrant()
    try:
        resp = qdrant.query_points(
            collection_name=INTERPRETATIONS_COLLECTION,
            query=query_vec,
            limit=k * 3,  # margen: se colapsa a 1 pasaje por fuente
            score_threshold=score_threshold,
        )
    except Exception:  # noqa: BLE001
        return []

    # `vectorize_consensus` comparte esta colección y marca sus puntos con
    # `source_id` NEGATIVO (-song_id) porque no son fuentes: son los consensos ya
    # destilados, que llegan a los generadores por su propio camino
    # (`fetch_distilled_for_song`). Se descartan aquí para no gastar huecos del top-k
    # en algo que luego no se podría rehidratar de `interpretation_sources`.
    excluded = set(exclude_kinds or ()) | {"fan_consensus"}
    # Mejor hit por fuente, preservando el orden por score que ya trae Qdrant.
    best: dict[int, dict[str, Any]] = {}
    for r in resp.points:
        p = r.payload or {}
        if (p.get("kind") or "") in excluded:
            continue
        try:
            sid = int(p["source_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if sid < 0:  # cinturón, por si algún payload viejo no trae `kind`
            continue
        if sid in best:
            continue
        best[sid] = {
            "source_id": sid,
            "chunk_index": int(p.get("chunk_index") or 0),
            "kind": p.get("kind") or "fuente",
            "title": p.get("title") or "",
            "author": p.get("author") or "",
            "url": p.get("url") or "",
            "score": float(r.score),
        }
        if len(best) >= k:
            break
    if not best:
        return []

    rows = (
        db.query(InterpretationSource.id, InterpretationSource.content_clean)
        .filter(InterpretationSource.id.in_(list(best)))
        .all()
    )
    texto = {i: c for i, c in rows}

    out: list[dict[str, Any]] = []
    for sid, meta in best.items():
        full = texto.get(sid) or ""
        if not full.strip():
            continue
        chunks = chunk_text(full)
        idx = meta["chunk_index"]
        frag = (chunks[idx] if 0 <= idx < len(chunks) else (chunks[0] if chunks else full))
        out.append({**meta, "fragmento": frag.strip()[:max_chars]})
    return out


# Boost factor aplicado al score RRF de un hit cuando su song_id aparece
# en las fuentes fan o en la letra completa vectorialmente cercanas a la query.
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
    start_seconds: int | None = None


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
def search_lyrics_full_for_song_ids(
    query_vec: list[float], k: int = 10, score_threshold: float = 0.32
) -> dict[int, float]:
    """Busca la letra COMPLETA de cada canción contra la query.

    Captura queries conceptuales de alto nivel cuando la canción habla del
    tema en su conjunto pero ningún chunk individual lo refleja.
    Devuelve {song_id: score}. Los hits boostean el RRF.
    """
    qdrant = get_qdrant()
    try:
        resp = qdrant.query_points(
            collection_name=LYRICS_FULL_COLLECTION,
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
