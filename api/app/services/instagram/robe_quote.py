"""Busca un verso de Robe / Extremoduro afín a un texto.

Antes Entre Noticias llamaba por HTTP al buscador de entreinteriores.com; ahora
que el pipeline vive DENTRO de RobeLyrics se hace la búsqueda in-process:
embedding + búsqueda vectorial sobre la colección de líneas. Así cada post
puede cerrar enlazando la actualidad con una frase del propio Robe.

Degradación elegante: ante cualquier fallo devuelve None y el post se publica
igualmente sin verso.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.db.models import Song
from app.services.embeddings import get_embedder
from app.services.retrieval import LINES_COLLECTION, vector_search

logger = logging.getLogger(__name__)


def _clean_song_title(title: str) -> str:
    """Quita sufijos de versión: '[En Directo]', '(Maqueta)', etc."""
    title = re.sub(r"\s*\[[^\]]*\]\s*$", "", title)
    title = re.sub(
        r"\s*\((?:en directo|directo|maqueta|remasterizad[ao])[^)]*\)\s*$",
        "", title, flags=re.IGNORECASE,
    )
    return title.strip()


def find_verse(db: Session, text: str) -> dict | None:
    """Devuelve el verso más afín a `text` o None.

    Resultado: {"line", "song", "artist", "year"}.
    """
    try:
        query_vec = get_embedder().embed_one(text[:480])
        hits = vector_search(LINES_COLLECTION, query_vec, k=3)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[robe_quote] búsqueda semántica falló: %s", exc)
        return None

    if not hits:
        return None
    top = hits[0]
    line = (top.text or "").strip()
    if not line:
        return None

    song = db.get(Song, top.song_id) if top.song_id else None
    if song is None:
        return {"line": line, "song": "", "artist": "Extremoduro", "year": None}

    album = song.album
    artist = album.artist if album is not None else None
    return {
        "line": line,
        "song": _clean_song_title(song.title),
        "artist": artist.name if artist is not None else "Extremoduro",
        "year": album.year if album is not None else None,
    }
