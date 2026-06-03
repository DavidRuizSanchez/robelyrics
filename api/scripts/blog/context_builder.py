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
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SeoContent
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
