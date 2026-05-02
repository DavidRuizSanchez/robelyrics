"""Reranker LLM con inyección de fan_context.

Para cada candidato del retrieval híbrido, recoge `SongInterpretation` (si
existe y confidence >= medium) y la añade al prompt como "Contexto del
universo Robe". Devuelve los top-K reordenados con justificación corta.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.db.models import Line, Song, SongInterpretation
from app.services.retrieval import Hit

RERANK_MODEL = "gpt-4o-mini"


@dataclass
class RerankedHit:
    line_text: str
    song_id: int
    line_index: int | None
    start_seconds: int | None
    context_before: list[str]
    context_after: list[str]
    fan_context: str | None
    fan_context_sources: list[dict[str, Any]]
    why: str
    # Metadatos de canción ya enriquecidos (vienen del payload)
    song: dict[str, Any]
    album: dict[str, Any]
    artist: dict[str, Any]


RERANK_SCHEMA = {
    "name": "rerank_result",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "ranked": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "candidate_idx": {"type": "integer"},
                        "why": {"type": "string"},
                    },
                    "required": ["candidate_idx", "why"],
                },
            }
        },
        "required": ["ranked"],
    },
    "strict": True,
}


SYSTEM_PROMPT = """Eres un experto en la obra de Extremoduro y Robe Iniesta. Tu tarea es elegir, de una lista de candidatos del catálogo, los versos que mejor se corresponden con la frase del usuario.

## Encaje válido (acepta estos)

1. **Directo**: el verso expresa lo mismo que la frase del usuario. Ej: "he comido demasiado" ↔ "el estómago me revienta".

2. **Metafórico**: el verso usa imágenes coherentes con el sentimiento. Ej: "se acabó lo bonito" ↔ "se acabó la primavera" (primavera = bien efímero). "Adentrarse en lo desconocido" ↔ "no hay vuelta atrás, llegué a lo más profundo".

3. **Contraste coherente**: el verso aborda el MISMO eje temático desde la polaridad opuesta. Ej: "he comido demasiado" ↔ "no he probado bocado" (ambos hablan de la relación con la comida, uno por exceso, otro por defecto). Si incluyes un contraste, el `why` lo deja claro ("desde la polaridad opuesta…", "contrapone…").

4. **Tangencial** pero coherente: el verso evoca un estado emocional o vital cercano, aunque la conexión no sea exacta. Ej: "estoy harto" ↔ "ya no aguanto más" (mismo malestar). Acepta estos cuando el tono y el universo son compatibles, pero el `why` debe articular la conexión.

## NO-encaje (descarta SIEMPRE — estos casos NO se rescatan)

- **Coincidencia léxica trivial sin tema en común**: una palabra suelta repetida en contextos distintos.
- **Generalización bullshit**: NO racionalices conexiones por categorías abstractas tipo "ambos hablan de exceso", "ambos son negativos", "ambos hablan de la vida". Esa abstracción es trampa. Si la query es "he comido demasiado" (tema: COMIDA, hartazgo gastronómico) y el verso es "demasiada droga" (tema: DROGAS, adicción), NO encajan, aunque ambos sean "exceso de algo". El nivel correcto de abstracción es el TEMA CONCRETO de la query, no una categoría difusa que englobe muchas cosas.
- **Tema concreto distinto** aunque suene poético o use palabra(s) en común.

Test mental: si tu `why` empieza con "ambos hablan de…" seguido de un concepto abstracto (exceso, dolor, vida, búsqueda…) que englobaría medio cancionero, el encaje no es real. Mejor descártalo.

## Reglas de salida

- **Devuelve hasta top_k candidatos** ordenados de mejor a peor encaje. Es preferible llenar el top_k con matches buenos y tangenciales que devolver muy pocos.
- **Pero descarta el ruido léxico**: si un candidato solo encaja por una palabra suelta y el resto del verso va por otro lado, no lo incluyas.
- **`why` corto** (1 frase, ≤25 palabras) que explique la conexión SEMÁNTICA. Si tu `why` se reduce a "comparten la palabra X", ese candidato no debe estar.
- Si hay "Contexto del universo Robe" para un candidato, úsalo como prueba de encaje.

Tu trabajo es ser un editor lúcido: ni dejas pasar el ruido, ni te quedas tan corto que el usuario no encuentre material."""


# --------------------------------------------------------------------------- #
# Enriquecimiento previo (contexto + fan_context)
# --------------------------------------------------------------------------- #
def fetch_song_context(
    db: Session,
    song_ids: set[int],
) -> dict[int, dict[str, Any]]:
    """Devuelve {song_id: {song, album, artist, fan_context, fan_sources}}."""
    if not song_ids:
        return {}
    songs = (
        db.query(Song)
        .filter(Song.id.in_(song_ids))
        .all()
    )
    out: dict[int, dict[str, Any]] = {}
    for s in songs:
        album = s.album
        artist = album.artist
        # fan_context (si existe interpretación con confidence medium o high)
        interp = s.interpretation
        fan_context = None
        fan_sources: list[dict[str, Any]] = []
        if interp and interp.confidence in ("high", "medium"):
            payload = interp.payload or {}
            fan_context = payload.get("fan_consensus") or None
            # Limitamos las fuentes citadas para no inflar respuesta
            for sid in (interp.source_ids or [])[:5]:
                fan_sources.append({"source_id": sid})
        out[s.id] = {
            "song": {
                "id": s.id,
                "title": s.title,
                "slug": s.slug,
                "youtube_id": s.youtube_id,
            },
            "album": {"title": album.title, "slug": album.slug, "year": album.year},
            "artist": {"slug": artist.slug, "name": artist.name},
            "fan_context": fan_context,
            "fan_sources": fan_sources,
            "_lyrics_clean": s.lyrics_clean or "",
        }
    return out


def fetch_line_neighbors(
    db: Session,
    requests_: list[tuple[int, int]],
    n_before: int = 2,
    n_after: int = 2,
) -> dict[tuple[int, int], tuple[list[str], list[str]]]:
    """Para una lista de (song_id, line_index), devuelve N líneas antes y después."""
    if not requests_:
        return {}
    song_ids = {sid for sid, _ in requests_}
    lines_by_song: dict[int, list[Line]] = {}
    for line in (
        db.query(Line)
        .filter(Line.song_id.in_(song_ids))
        .order_by(Line.song_id, Line.line_index)
        .all()
    ):
        lines_by_song.setdefault(line.song_id, []).append(line)

    out: dict[tuple[int, int], tuple[list[str], list[str]]] = {}
    for sid, idx in requests_:
        all_lines = lines_by_song.get(sid, [])
        before = [l.text for l in all_lines if 0 <= idx - n_before <= l.line_index < idx][:n_before]
        after = [l.text for l in all_lines if idx < l.line_index <= idx + n_after][:n_after]
        out[(sid, idx)] = (before, after)
    return out


# --------------------------------------------------------------------------- #
# Llamada al LLM
# --------------------------------------------------------------------------- #
@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
    reraise=True,
)
def _call_rerank(client: OpenAI, system: str, user: str) -> str:
    resp = client.chat.completions.create(
        model=RERANK_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_schema", "json_schema": RERANK_SCHEMA},
        temperature=0.2,
    )
    return resp.choices[0].message.content or "{}"


def build_rerank_prompt(query: str, candidates: list[Hit], song_ctx: dict[int, dict[str, Any]]) -> str:
    parts = [f'# Frase del usuario\n"{query}"\n\n# Candidatos\n']
    for i, c in enumerate(candidates):
        ctx = song_ctx.get(c.song_id, {})
        song_meta = ctx.get("song", {})
        album_meta = ctx.get("album", {})
        artist_meta = ctx.get("artist", {})
        parts.append(
            f"\n[{i}] «{c.text}»\n"
            f"    {artist_meta.get('name', '?')} — {song_meta.get('title', '?')} / "
            f"{album_meta.get('title', '?')} ({album_meta.get('year', '?')})"
        )
        fan_ctx = ctx.get("fan_context")
        if fan_ctx:
            parts.append(f"    Contexto del universo Robe: {fan_ctx[:500]}")
    parts.append(
        "\n\n# Tarea\n"
        "Elige los candidatos que mejor casan con la frase del usuario, en orden. "
        "Si ninguno casa bien, devuelve `ranked: []`."
    )
    return "\n".join(parts)


def rerank(
    query: str,
    candidates: list[Hit],
    db: Session,
    top_k: int = 5,
) -> list[RerankedHit]:
    if not candidates:
        return []
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY no configurada")
    client = OpenAI(api_key=settings.openai_api_key)

    # Enriquecer con metadata + fan_context
    song_ctx = fetch_song_context(db, {c.song_id for c in candidates})

    # Llamar al LLM
    user_prompt = build_rerank_prompt(query, candidates, song_ctx)
    try:
        content = _call_rerank(client, SYSTEM_PROMPT, user_prompt)
    except Exception:  # noqa: BLE001
        # Si tras retries falla, fallback: devolver candidatos en orden de retrieval
        return _fallback_no_rerank(candidates, song_ctx, db, top_k)

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return _fallback_no_rerank(candidates, song_ctx, db, top_k)

    ranked_meta = parsed.get("ranked", [])[:top_k]

    # Pre-fetch de neighbors solo para los seleccionados (más eficiente)
    selected_pairs: list[tuple[int, int]] = []
    for r in ranked_meta:
        idx = r.get("candidate_idx")
        if idx is None or idx >= len(candidates):
            continue
        c = candidates[idx]
        if c.line_index is not None:
            selected_pairs.append((c.song_id, c.line_index))
    neighbors = fetch_line_neighbors(db, selected_pairs, n_before=2, n_after=2)

    out: list[RerankedHit] = []
    for r in ranked_meta:
        idx = r.get("candidate_idx")
        if idx is None or idx >= len(candidates):
            continue
        c = candidates[idx]
        ctx = song_ctx.get(c.song_id, {})
        before: list[str] = []
        after: list[str] = []
        if c.line_index is not None:
            before, after = neighbors.get((c.song_id, c.line_index), ([], []))
        out.append(
            RerankedHit(
                line_text=c.text,
                song_id=c.song_id,
                line_index=c.line_index,
                start_seconds=c.start_seconds,
                context_before=before,
                context_after=after,
                fan_context=ctx.get("fan_context"),
                fan_context_sources=ctx.get("fan_sources", []),
                why=r.get("why", ""),
                song=ctx.get("song", {}),
                album=ctx.get("album", {}),
                artist=ctx.get("artist", {}),
            )
        )
    return out


def _fallback_no_rerank(
    candidates: list[Hit],
    song_ctx: dict[int, dict[str, Any]],
    db: Session,
    top_k: int,
) -> list[RerankedHit]:
    """Si el LLM falla, devolvemos los top_k del retrieval con why vacío."""
    selected = candidates[:top_k]
    neighbors = fetch_line_neighbors(
        db,
        [(c.song_id, c.line_index) for c in selected if c.line_index is not None],
    )
    out: list[RerankedHit] = []
    for c in selected:
        ctx = song_ctx.get(c.song_id, {})
        before: list[str] = []
        after: list[str] = []
        if c.line_index is not None:
            before, after = neighbors.get((c.song_id, c.line_index), ([], []))
        out.append(
            RerankedHit(
                line_text=c.text,
                song_id=c.song_id,
                line_index=c.line_index,
                start_seconds=c.start_seconds,
                context_before=before,
                context_after=after,
                fan_context=ctx.get("fan_context"),
                fan_context_sources=ctx.get("fan_sources", []),
                why="",
                song=ctx.get("song", {}),
                album=ctx.get("album", {}),
                artist=ctx.get("artist", {}),
            )
        )
    return out
