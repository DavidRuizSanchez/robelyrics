"""Destila las fuentes fan en una `SongInterpretation` por canción.

Para cada Song en la BD:
  1. Selecciona las InterpretationSource cuyo `content_clean` mencione
     explícitamente el título de la canción (case+accent insensitive).
  2. Si hay ≥1 fuente, llama a GPT-4o-mini con structured outputs.
  3. Valida que CADA claim del JSON cite al menos un source_id presente
     en el set entregado (anti-alucinación).
  4. Calcula confidence:
       high   → ≥3 fuentes distintas
       medium → 2 fuentes
       low    → 1 fuente
  5. Upsert en song_interpretations.

⚠️ REQUIERE Fase 1 ejecutada: las songs deben estar en BD con sus letras.
   Si no, este script no encuentra nada que destilar.

Ejecución:
  docker compose exec api python -m scripts.research.distill
  docker compose exec api python -m scripts.research.distill --song-slug salir
"""
from __future__ import annotations

import argparse
import json
import re
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
from qdrant_client import QdrantClient
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.db.models import InterpretationSource, Song, SongInterpretation
from scripts.research.common import get_session, log, normalize

EMBED_MODEL = "text-embedding-3-large"
INTERPRETATIONS_COLLECTION = "interpretations_v1"
VECTOR_FALLBACK_THRESHOLD = 0.40  # cos similarity mínima
VECTOR_FALLBACK_MIN_SOURCES = 2   # si tras matcher textual hay menos, hacer vector search
VECTOR_FALLBACK_K = 5              # top-K vectores a considerar

DISTILL_MODEL = "gpt-4o-mini"

# Schema OpenAI structured outputs (JSON Schema dialect 2020-12, subset).
# Cada claim DEBE incluir source_ids no vacío para anti-alucinación.
DISTILL_SCHEMA: dict[str, Any] = {
    "name": "song_interpretation",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "themes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "theme": {"type": "string"},
                        "source_ids": {"type": "array", "items": {"type": "integer"}, "minItems": 1},
                    },
                    "required": ["theme", "source_ids"],
                },
            },
            "key_metaphors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "phrase": {"type": "string"},
                        "meaning": {"type": "string"},
                        "source_ids": {"type": "array", "items": {"type": "integer"}, "minItems": 1},
                    },
                    "required": ["phrase", "meaning", "source_ids"],
                },
            },
            "references": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "type": {"type": "string", "enum": ["biographical", "intertextual", "cultural"]},
                        "description": {"type": "string"},
                        "source_ids": {"type": "array", "items": {"type": "integer"}, "minItems": 1},
                    },
                    "required": ["type", "description", "source_ids"],
                },
            },
            "fan_consensus": {"type": "string"},
            "fan_consensus_citations": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 1,
            },
        },
        "required": ["themes", "key_metaphors", "references", "fan_consensus", "fan_consensus_citations"],
    },
    "strict": True,
}


SYSTEM_PROMPT = """Eres un analista cultural especializado en la obra de Extremoduro y Robe Iniesta.
Tu tarea es destilar el conocimiento de fans sobre una canción concreta.

REGLAS ABSOLUTAS:
1. Cada claim (tema, metáfora, referencia, frase del consenso) DEBE estar respaldado por al menos un source_id de los entregados. Si no encuentras respaldo, NO incluyas el claim.
2. NO te inventes datos biográficos ni fechas. Si los fans no lo dicen, no lo digas.
3. Si las fuentes no aportan nada útil sobre la canción, devuelve arrays vacíos para themes/key_metaphors/references y un fan_consensus diciendo que no hay consenso fan documentado.
4. Escribe en español. fan_consensus: 200-400 palabras. Tono neutral analítico.
5. Las fuentes pueden contradecirse. Si lo hacen, refleja la divergencia ("algunos fans interpretan X, otros Y") y cita ambos source_ids."""


def aliases_for(song: Song) -> list[str]:
    """Genera variantes del título para mejorar el matching.

    Ejemplos:
      "Caballero andante (¡No me dejéis asíii!)" → ["Caballero andante (¡No me dejéis asíii!)",
                                                    "Caballero andante"]
      "Tercer Movimiento: Lo de Dentro" → ["Tercer Movimiento: Lo de Dentro", "Lo de Dentro"]
      "La Vereda de la Puerta de Atrás" → [original + slug "la-vereda-de-la-puerta-de-atras"]

    Filtros: aliases <4 chars o palabras genéricas (artículos, conjunciones) descartados.
    """
    out: list[str] = [song.title]
    # Sin paréntesis
    no_paren = re.sub(r"\s*\([^)]*\)\s*", "", song.title).strip()
    if no_paren and no_paren != song.title:
        out.append(no_paren)
    # Sufijo tras ":"
    if ":" in song.title:
        suffix = song.title.split(":", 1)[1].strip()
        if suffix:
            out.append(suffix)
    # Slug también, los fans a veces lo copian de URLs
    if song.slug:
        out.append(song.slug.replace("-", " "))
    # Filtrar duplicados y candidatos demasiado cortos / genéricos
    GENERIC = {"si", "no", "tu", "te", "yo", "el", "la", "ama"}
    seen: set[str] = set()
    cleaned: list[str] = []
    for a in out:
        n = normalize(a)
        if not n or len(n) < 4 or n in GENERIC or n in seen:
            continue
        seen.add(n)
        cleaned.append(a)
    return cleaned


def _matches_with_boundaries(haystack_norm: str, needle_norm: str) -> bool:
    """Match por substring exigiendo word-boundaries (puntuación / espacios) alrededor."""
    if not needle_norm:
        return False
    pattern = r"(^|[^a-z0-9])" + re.escape(needle_norm) + r"([^a-z0-9]|$)"
    return bool(re.search(pattern, haystack_norm))


def select_sources_for_song(db, song: Song) -> tuple[list[InterpretationSource], list[str]]:
    """Devuelve (sources, debug_aliases_used).

    Estrategia:
      1. Genera aliases del título (sin paréntesis, sufijo tras ':', slug humanizado).
      2. Para cada alias, ILIKE %alias% en content_clean (uno o varios alias en SQL via OR).
      3. Filtra en Python con word-boundary regex sobre la versión normalizada (sin acentos).
    """
    aliases = aliases_for(song)
    if not aliases:
        return [], []

    # SQL: OR de ILIKEs por cada alias. ILIKE no quita acentos pero los fans
    # escriben "primavera" igual con o sin tilde, y el filtro Python con
    # normalize() lo arregla post-hoc.
    or_clauses = [InterpretationSource.content_clean.ilike(f"%{a}%") for a in aliases]
    stmt = select(InterpretationSource).where(or_(*or_clauses))
    candidates = db.execute(stmt).scalars().all()

    aliases_norm = [normalize(a) for a in aliases]
    out: list[InterpretationSource] = []
    for c in candidates:
        if not c.content_clean:
            continue
        haystack = normalize(c.content_clean)
        if any(_matches_with_boundaries(haystack, a) for a in aliases_norm):
            out.append(c)
    return out, aliases


def vector_search_fallback(
    qdrant: QdrantClient,
    openai: OpenAI,
    song: Song,
    already_matched_ids: set[int],
    db,
) -> list[InterpretationSource]:
    """Busca en interpretations_v1 fuentes semánticamente cercanas a la letra.

    Útil cuando las fuentes no nombran la canción literalmente (entrevistas
    sobre temas, análisis genéricos del disco, etc.).
    """
    if not song.lyrics_clean:
        return []
    query_text = song.lyrics_clean[:4000]
    try:
        emb_resp = openai.embeddings.create(model=EMBED_MODEL, input=query_text)
        query_vec = emb_resp.data[0].embedding
    except Exception as e:  # noqa: BLE001
        log(f"  vector fallback embed error {song.title}: {type(e).__name__}", "warn")
        return []

    try:
        # qdrant-client 1.17+: search() eliminado, usar query_points() con query=vector
        resp = qdrant.query_points(
            collection_name=INTERPRETATIONS_COLLECTION,
            query=query_vec,
            limit=VECTOR_FALLBACK_K,
            score_threshold=VECTOR_FALLBACK_THRESHOLD,
        )
        hits = resp.points
    except Exception as e:  # noqa: BLE001
        log(f"  vector fallback search error {song.title}: {type(e).__name__}: {e}", "warn")
        return []

    new_source_ids: list[int] = []
    for h in hits:
        sid = (h.payload or {}).get("source_id")
        if sid is None or sid in already_matched_ids:
            continue
        new_source_ids.append(int(sid))
    if not new_source_ids:
        return []

    rows = db.execute(
        select(InterpretationSource).where(InterpretationSource.id.in_(new_source_ids))
    ).scalars().all()
    return list(rows)


def build_user_prompt(song: Song, sources: list[InterpretationSource]) -> str:
    parts = [
        f"# Canción\n{song.title} — {song.album.artist.name} / {song.album.title} ({song.album.year})",
    ]
    if song.lyrics_clean:
        parts.append(f"\n# Letra\n{song.lyrics_clean[:3000]}")  # cap por si acaso
    parts.append("\n# Fuentes (fan-content)\n")
    for s in sources:
        parts.append(f"\n## source_id={s.id} · kind={s.kind} · author={s.author or 'anon'}")
        if s.title:
            parts.append(f"### {s.title}")
        text = (s.content_clean or "")[:1500]  # truncar para no inflar el prompt
        parts.append(text)
    parts.append(
        "\n# Tarea\nDestila la interpretación fan de esta canción según el schema. "
        "Recuerda: cada claim debe citar al menos un source_id de los anteriores."
    )
    return "\n".join(parts)


def filter_uncited_claims(payload: dict[str, Any], valid_ids: set[int]) -> dict[str, Any]:
    """Quita claims que citen source_ids no presentes en el set entregado."""
    cleaned: dict[str, Any] = {"themes": [], "key_metaphors": [], "references": []}
    for key in ("themes", "key_metaphors", "references"):
        for item in payload.get(key, []):
            sids = [sid for sid in item.get("source_ids", []) if sid in valid_ids]
            if sids:
                item["source_ids"] = sids
                cleaned[key].append(item)
    cleaned["fan_consensus"] = payload.get("fan_consensus", "")
    cleaned["fan_consensus_citations"] = [
        sid for sid in payload.get("fan_consensus_citations", []) if sid in valid_ids
    ]
    return cleaned


def confidence_for(n_sources: int) -> str:
    if n_sources >= 3:
        return "high"
    if n_sources == 2:
        return "medium"
    return "low"


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
    reraise=True,
)
def _call_openai(client: OpenAI, system: str, user: str) -> str:
    resp = client.chat.completions.create(
        model=DISTILL_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_schema", "json_schema": DISTILL_SCHEMA},
        temperature=0.3,
    )
    return resp.choices[0].message.content or "{}"


def distill_song(client: OpenAI, song: Song, sources: list[InterpretationSource]) -> dict[str, Any] | None:
    user_prompt = build_user_prompt(song, sources)
    try:
        content = _call_openai(client, SYSTEM_PROMPT, user_prompt)
    except Exception as e:  # noqa: BLE001
        # Tras 5 retries con backoff, si sigue cayendo, log y skip
        log(f"  openai error tras retry: {type(e).__name__}: {e}", "warn")
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        log(f"  JSON parse error: {e}", "warn")
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--song-slug", help="Procesar solo una canción (debug)")
    parser.add_argument("--limit", type=int, default=None, help="Procesar solo N canciones")
    parser.add_argument("--no-vector-fallback", action="store_true", help="Desactiva vector search")
    parser.add_argument("--only-missing", action="store_true",
                        help="Solo canciones sin SongInterpretation aún")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada — abortando", "err")
        return
    client = OpenAI(api_key=settings.openai_api_key)
    qdrant = None
    if not args.no_vector_fallback:
        try:
            qdrant = QdrantClient(url=settings.qdrant_url)
        except Exception as e:  # noqa: BLE001
            log(f"qdrant no disponible: {e}. Continuando sin vector fallback.", "warn")
            qdrant = None

    n_done = 0
    n_skipped_no_sources = 0
    n_skipped_error = 0
    n_with_vector = 0

    # Carga la lista de slugs en una sesión rápida y luego procesa cada
    # canción en su propia sesión (commit-per-song). Si crashea el script,
    # solo perdemos la canción en curso, no las anteriores.
    with get_session() as db:
        q = db.query(Song.slug)
        if args.song_slug:
            q = q.filter(Song.slug == args.song_slug)
        if args.only_missing:
            q = q.outerjoin(SongInterpretation, SongInterpretation.song_id == Song.id)
            q = q.filter(SongInterpretation.id.is_(None))
        slugs = [r[0] for r in q.all()]
    if not slugs:
        log("Sin canciones que procesar.", "warn")
        return
    log(f"canciones a procesar: {len(slugs)}")

    for slug in slugs:
        if args.limit and n_done >= args.limit:
            break

        with get_session() as db:
            song = db.query(Song).filter(Song.slug == slug).first()
            if not song:
                continue

            sources, aliases = select_sources_for_song(db, song)

            used_vector = False
            if qdrant is not None and len(sources) < VECTOR_FALLBACK_MIN_SOURCES:
                already = {s.id for s in sources}
                vec_sources = vector_search_fallback(qdrant, client, song, already, db)
                if vec_sources:
                    sources = sources + vec_sources
                    used_vector = True

            if not sources:
                n_skipped_no_sources += 1
                continue

            tag = " (+vec)" if used_vector else ""
            log(f"distill: {song.title} · {len(sources)} fuentes{tag}")
            payload = distill_song(client, song, sources)
            if payload is None:
                n_skipped_error += 1
                continue

            valid_ids = {s.id for s in sources}
            cleaned = filter_uncited_claims(payload, valid_ids)
            cited_sources = sorted(
                set(
                    sid
                    for key in ("themes", "key_metaphors", "references")
                    for item in cleaned.get(key, [])
                    for sid in item.get("source_ids", [])
                )
                | set(cleaned.get("fan_consensus_citations", []))
            )
            confidence = confidence_for(len(cited_sources))

            stmt = (
                pg_insert(SongInterpretation)
                .values(
                    song_id=song.id,
                    payload=cleaned,
                    confidence=confidence,
                    source_ids=cited_sources,
                )
                .on_conflict_do_update(
                    index_elements=["song_id"],
                    set_={
                        "payload": cleaned,
                        "confidence": confidence,
                        "source_ids": cited_sources,
                    },
                )
            )
            db.execute(stmt)
            # commit al cerrar el `with get_session()`
        n_done += 1
        if used_vector:
            n_with_vector += 1

    log(
        f"destiladas: {n_done} (de las cuales {n_with_vector} usaron vector fallback) · "
        f"skip-sin-fuentes: {n_skipped_no_sources} · skip-error: {n_skipped_error}",
        "ok",
    )


if __name__ == "__main__":
    main()
