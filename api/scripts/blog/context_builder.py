"""Constructores de CONTEXTO para los posts de blog.

Reutiliza los helpers ya existentes de `scripts.seo.common` (NO los reescribe;
los importa) para producir un único string de contexto rico por entidad
(canción / disco / artista / taxonomía) que se inyecta como `context=` en los
generadores de `app.services.content_generator`.

Cada función combina, con encabezados legibles y caps razonables:
  - CONSENSO FAN DESTILADO (SongInterpretation.payload) → da la lectura
    interpretativa consensuada.
  - FUENTES (fan-content/prensa que menciona la entidad) → datos duros.
  - INTRO del cuerpo SEO (SeoContent.body_md) ya generado para esa entidad.

El SeoContent se busca por (entity_type, entity_id), con
entity_type ∈ {'song','album','artist','theme','place','concept'}.

Filosofía: el string resultante es MATERIA PRIMA documentada para que la pieza
salga con chicha concreta y no genérica. Si una entidad no tiene contexto, las
funciones devuelven "" (string vacío) — el caller pasa eso y el generador ya
sabe escribir poco y honesto sin rellenar.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Album, SeoContent
from scripts.seo.common import (
    fetch_distilled_for_album,
    fetch_distilled_for_artist,
    fetch_distilled_for_song,
    fetch_sources_for_album,
    fetch_sources_for_artist,
    fetch_sources_for_song,
    format_distilled_block,
    format_sources_block,
)

logger = logging.getLogger(__name__)

# Cap por parte (consenso / fuentes / intro SEO). El generador vuelve a cortar
# el total a ~3000 chars, así que esto solo equilibra el reparto.
PART_CAP = 1500


def _seo_body(db: Session, entity_type: str, entity_id: int) -> str:
    """Intro del cuerpo SEO ya generado para (entity_type, entity_id)."""
    try:
        row = db.execute(
            select(SeoContent).where(
                SeoContent.entity_type == entity_type,
                SeoContent.entity_id == entity_id,
            )
        ).scalar_one_or_none()
    except Exception as exc:  # pragma: no cover - defensivo
        logger.warning("context_builder: SeoContent lookup falló: %s", exc)
        return ""
    if not row or not row.body_md:
        return ""
    return (row.body_md or "").strip()[:PART_CAP]


def _assemble(parts: list[tuple[str, str]]) -> str:
    """Une bloques (encabezado, cuerpo) no vacíos con separadores legibles."""
    blocks: list[str] = []
    for header, body in parts:
        body = (body or "").strip()
        if not body:
            continue
        blocks.append(f"== {header} ==\n{body}")
    return "\n\n".join(blocks).strip()


def song_context(db: Session, song_id: int) -> str:
    """Contexto rico de una canción: consenso destilado + fuentes + intro SEO."""
    try:
        distilled = fetch_distilled_for_song(db, song_id)
        sources = fetch_sources_for_song(db, song_id)
    except Exception as exc:  # pragma: no cover - defensivo
        logger.warning("song_context(%s) falló al recopilar: %s", song_id, exc)
        distilled, sources = None, []

    consenso = format_distilled_block(distilled)
    fuentes = format_sources_block(sources) if sources else ""
    seo = _seo_body(db, "song", song_id)

    return _assemble([
        ("CONSENSO FAN", consenso[:PART_CAP]),
        ("FUENTES", fuentes[:PART_CAP]),
        ("ARTÍCULO SEO (intro)", seo),
    ])


def album_context(db: Session, album_id: int) -> str:
    """Contexto rico de un disco: consenso destilado de sus canciones +
    fuentes que mencionan el disco + intro del SEO del álbum."""
    try:
        distilled = fetch_distilled_for_album(db, album_id)
        sources = fetch_sources_for_album(db, album_id)
    except Exception as exc:  # pragma: no cover - defensivo
        logger.warning("album_context(%s) falló al recopilar: %s", album_id, exc)
        distilled, sources = [], []

    consenso = format_distilled_block(distilled)
    fuentes = format_sources_block(sources) if sources else ""
    seo = _seo_body(db, "album", album_id)

    return _assemble([
        ("CONSENSO FAN (canciones del disco)", consenso[:PART_CAP]),
        ("FUENTES", fuentes[:PART_CAP]),
        ("ARTÍCULO SEO (intro)", seo),
    ])


def artist_context(db: Session, artist_id: int) -> str:
    """Contexto rico de un artista/figura: consenso destilado de su obra +
    fuentes que lo mencionan + intro del SEO del artista."""
    try:
        distilled = fetch_distilled_for_artist(db, artist_id)
        sources = fetch_sources_for_artist(db, artist_id)
    except Exception as exc:  # pragma: no cover - defensivo
        logger.warning("artist_context(%s) falló al recopilar: %s", artist_id, exc)
        distilled, sources = [], []

    consenso = format_distilled_block(distilled)
    fuentes = format_sources_block(sources) if sources else ""
    seo = _seo_body(db, "artist", artist_id)

    return _assemble([
        ("CONSENSO FAN (su obra)", consenso[:PART_CAP]),
        ("FUENTES", fuentes[:PART_CAP]),
        ("ARTÍCULO SEO (intro)", seo),
    ])


def taxonomy_context(
    db: Session,
    songs_titles_or_song_ids: list[Any] | None,
    seo_body: str | None,
) -> str:
    """Contexto para una taxonomía (tema/lugar/concepto).

    Combina el consenso destilado de sus canciones cuando se reciben song_ids
    (enteros); si solo se reciben títulos (strings), no hay forma directa de
    destilar y nos quedamos con el `seo_body` que aporte el caller.
    """
    consenso = ""
    ids = [
        s for s in (songs_titles_or_song_ids or [])
        if isinstance(s, int)
    ]
    if ids:
        try:
            distilled: list[dict[str, Any]] = []
            for sid in ids[:14]:
                d = fetch_distilled_for_song(db, sid)
                if d:
                    distilled.append(d)
            consenso = format_distilled_block(distilled)
        except Exception as exc:  # pragma: no cover - defensivo
            logger.warning("taxonomy_context falló al destilar: %s", exc)
            consenso = ""

    seo = (seo_body or "").strip()[:PART_CAP]

    return _assemble([
        ("CONSENSO FAN (canciones del tema)", consenso[:PART_CAP]),
        ("ARTÍCULO SEO (intro)", seo),
    ])


# --------------------------------------------------------------------------- #
# Contexto de GIRAS — anclado en el corpus real (entrevistas + fan-content +
# digests de libros). Ver feedback: el contenido se genera con RAG, no a mano.
# --------------------------------------------------------------------------- #
_REFERENCE_DIR = Path(__file__).resolve().parents[2] / "data" / "reference"


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _norm(s: str) -> str:
    return _strip_accents(s or "").lower()


@lru_cache(maxsize=1)
def _reference_lines() -> tuple[str, ...]:
    """Líneas con sustancia de los digests de libros (data/reference/*.md).

    Cada bullet de esos ficheros es un hecho verificable auto-contenido; nos
    quedamos con las líneas largas (descarta encabezados y ruido).
    """
    lines: list[str] = []
    try:
        for md in sorted(_REFERENCE_DIR.glob("*.md")):
            for raw in md.read_text(encoding="utf-8").splitlines():
                t = raw.strip().lstrip("#-*• ").strip()
                if len(t) >= 40:
                    lines.append(t)
    except Exception as exc:  # pragma: no cover - defensivo
        logger.warning("_reference_lines falló leyendo %s: %s", _REFERENCE_DIR, exc)
        return ()
    return tuple(lines)


def _reference_snippets(terms: list[str], max_chars: int = 900) -> str:
    """Líneas de los digests que mencionan algún término de la gira (año,
    título del disco). Hechos reales de los libros, no inventados."""
    norm_terms = [_norm(t) for t in terms if t and len(t) >= 4]
    if not norm_terms:
        return ""
    picked: list[str] = []
    seen: set[str] = set()
    total = 0
    for line in _reference_lines():
        nline = _norm(line)
        if any(t in nline for t in norm_terms) and line not in seen:
            seen.add(line)
            picked.append(line)
            total += len(line)
            if total >= max_chars:
                break
    return "\n".join(f"- {ln}" for ln in picked)


def _format_voice_block(passages: list[dict[str, Any]]) -> str:
    """Formatea los pasajes de robe_voice_v1 (lo que dijo Robe) etiquetando
    tipo y fuente, para que el generador lo trate como palabra suya real."""
    out: list[str] = []
    for p in passages:
        frag = (p.get("fragmento") or "").strip()
        if not frag:
            continue
        tipo = p.get("tipo") or "entrevista"
        titulo = p.get("titulo") or "Robe"
        out.append(f"[{tipo} · {titulo}] «{frag}»")
    return "\n".join(out)


def tour_context(db: Session, tour: dict[str, Any]) -> str:
    """Contexto rico de una GIRA anclado en el corpus real:

      - LO QUE DIJO ROBE: pasajes de entrevistas/citas suyas (robe_voice_v1),
        recuperados por similitud semántica con la gira.
      - EL DISCO Y SU RECEPCIÓN: consenso fan + fuentes del disco protagonista
        (reutiliza album_context si `tour['album_slug']` casa con un álbum).
      - HECHOS DE LOS LIBROS: líneas de los digests (data/reference/*.md) que
        mencionan el disco o los años de la gira.
      - DATOS BASE: el bloque curado a mano del propio tour (ancla mínima).

    Best-effort: si una fuente falla o no hay material, se omite ese bloque.
    """
    title = tour.get("title", "")
    base_ctx = (tour.get("context") or "").strip()
    album_slug = tour.get("album_slug")

    # Disco protagonista (para album_context y para los términos de búsqueda).
    album = None
    if album_slug:
        try:
            album = db.execute(
                select(Album).where(Album.slug == album_slug)
            ).scalar_one_or_none()
        except Exception as exc:  # pragma: no cover - defensivo
            logger.warning("tour_context: lookup álbum %s falló: %s", album_slug, exc)

    # 1. Voz de Robe por RAG sobre robe_voice_v1.
    voice_block = ""
    try:
        from app.services.embeddings import get_embedder
        from app.services.retrieval import search_robe_voice

        qvec = get_embedder().embed_one(f"{title}. {base_ctx}")
        voice_block = _format_voice_block(search_robe_voice(qvec, k=6))
    except Exception as exc:  # pragma: no cover - defensivo
        logger.warning("tour_context: RAG voz de Robe falló: %s", exc)

    # 2. Disco protagonista: consenso fan + fuentes documentadas.
    album_block = ""
    if album is not None:
        try:
            album_block = album_context(db, album.id)
        except Exception as exc:  # pragma: no cover - defensivo
            logger.warning("tour_context: album_context(%s) falló: %s", album.id, exc)

    # 3. Hechos verificables de los libros (por año + título del disco).
    years = list(dict.fromkeys(re.findall(r"\b(?:19|20)\d{2}\b", base_ctx)))
    terms = list(years)
    if album is not None:
        terms.append(album.title)
    refs = _reference_snippets(terms)

    return _assemble([
        ("DATOS BASE DE LA GIRA", base_ctx[:700]),
        ("LO QUE DIJO ROBE (entrevistas/citas suyas — parafrasea, no cites literal)", voice_block[:1100]),
        ("HECHOS VERIFICADOS DE LOS LIBROS", refs[:700]),
        ("EL DISCO Y SU RECEPCIÓN", album_block[:500]),
    ])
