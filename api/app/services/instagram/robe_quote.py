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
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from app.db.models import Song
from app.services.embeddings import get_embedder
from app.services.retrieval import LINES_COLLECTION, vector_search

logger = logging.getLogger(__name__)

# Versos curados de canciones fuera del corpus (colaboraciones de Robe, etc.).
# Ver data/external_verses.yaml. Verificados a mano; nunca inventados.
_EXTERNAL_PATH = Path(__file__).resolve().parents[3] / "data" / "external_verses.yaml"

# Por debajo de este score coseno el verso no es lo bastante afín al tema:
# mejor publicar sin verso que con uno que no pega (p.ej. "cancioncita
# conmovedora" en una noticia sobre una colaboración).
MIN_SCORE = 0.30


def _clean_song_title(title: str) -> str:
    """Quita sufijos de versión: '[En Directo]', '(Maqueta)', etc."""
    title = re.sub(r"\s*\[[^\]]*\]\s*$", "", title)
    title = re.sub(
        r"\s*\((?:en directo|directo|maqueta|remasterizad[ao])[^)]*\)\s*$",
        "", title, flags=re.IGNORECASE,
    )
    return title.strip()


def _norm_line(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    ).lower()


@lru_cache(maxsize=1)
def _external_verses() -> list[dict]:
    try:
        data = yaml.safe_load(_EXTERNAL_PATH.read_text(encoding="utf-8")) or {}
        return data.get("versos") or []
    except Exception:  # noqa: BLE001
        return []


def _external_verse(text: str) -> dict | None:
    """Si el tema menciona una canción del dataset curado externo, devuelve su
    verso verificado (prioridad sobre el corpus). None si no aplica."""
    ntext = _strip_accents(text)
    for v in _external_verses():
        verse = (v.get("verse") or "").strip()
        if not verse:
            continue
        aliases = v.get("aliases") or ([v["song"]] if v.get("song") else [])
        for a in aliases:
            if a and _strip_accents(a) in ntext:
                return {
                    "line": verse,
                    "song": v.get("song", ""),
                    "artist": v.get("artist", "") or "Extremoduro",
                    "year": v.get("year"),
                }
    return None


def _mentioned_song_ids(db: Session, text: str) -> set[int]:
    """song_id de canciones del catálogo cuyo título aparece literalmente en el
    texto del tema (títulos de >=5 caracteres, para evitar falsos positivos).

    Permite priorizar un verso de LA canción de la que va la noticia."""
    ntext = _strip_accents(text)
    out: set[int] = set()
    try:
        for sid, title in db.query(Song.id, Song.title).all():
            t = _strip_accents(_clean_song_title(title))
            if len(t) >= 5 and t in ntext:
                out.add(sid)
    except Exception:  # noqa: BLE001
        return set()
    return out


def find_verse(
    db: Session, text: str, exclude_lines: set[str] | None = None
) -> dict | None:
    """Devuelve el verso más afín a `text` o None.

    `exclude_lines` (normalizadas) son versos usados recientemente: se saltan
    para no repetir el mismo verso en posts consecutivos.

    Prioriza un verso de la canción mencionada explícitamente en el tema; si no
    hay, el mejor hit semántico que supere `MIN_SCORE` (si nada lo supera,
    devuelve None: mejor sin verso que con uno que no pega).

    Resultado: {"line", "song", "artist", "year"}.
    """
    exclude = {_norm_line(x) for x in (exclude_lines or set())}

    # Prioridad máxima: si el tema va de una canción del dataset curado externo
    # (colaboraciones de Robe fuera del corpus), usar SU verso verificado.
    ext = _external_verse(text)
    if ext and _norm_line(ext["line"]) not in exclude:
        return ext

    try:
        query_vec = get_embedder().embed_one(text[:480])
        hits = vector_search(LINES_COLLECTION, query_vec, k=10)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[robe_quote] búsqueda semántica falló: %s", exc)
        return None

    if not hits:
        return None

    def _usable(h) -> bool:
        return bool((h.text or "").strip()) and _norm_line(h.text) not in exclude

    mentioned = _mentioned_song_ids(db, text)
    top = None
    # 1) Preferir un verso de la canción de la que va el tema (pertinencia alta).
    if mentioned:
        top = next((h for h in hits if h.song_id in mentioned and _usable(h)), None)
    # 2) Si no, el mejor hit afín no usado recientemente.
    if top is None:
        top = next((h for h in hits if _usable(h)), None)
    if top is None:
        return None
    # Umbral de relevancia (salvo que sea de una canción ya mencionada, donde la
    # pertinencia está garantizada): no forzar un verso poco afín.
    if top.song_id not in mentioned and (top.score or 0.0) < MIN_SCORE:
        logger.info("[robe_quote] sin verso afín (mejor score %.3f < %.2f)",
                    top.score or 0.0, MIN_SCORE)
        return None
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
