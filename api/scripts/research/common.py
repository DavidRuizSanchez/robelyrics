"""Utilidades compartidas por todos los scripts de Fase 0 (research).

Funciones:
    - log()                 print con timestamp + nivel
    - load_sources_yaml()   parsea data/sources.yaml
    - load_discography()    parsea data/discography.yaml
    - get_session()         context manager con SQLAlchemy session
    - upsert_source()       inserta o actualiza una InterpretationSource
    - find_referenced_titles()  detecta menciones de canciones en un texto
    - clean_text()          normaliza espacios, decode entities
    - retry_request()       wrapper tenacity para HTTP requests
"""
from __future__ import annotations

import html
import re
import sys
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential

from app.db.models import Album, Artist, InterpretationSource, Song
from app.db.session import SessionLocal

# /app/scripts/research/common.py → parents[2] = /app, /app/data está montado por docker-compose
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


# --------------------------------------------------------------------------- #
# Logging mínimo
# --------------------------------------------------------------------------- #
def log(msg: str, level: str = "info") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = {"info": "[·]", "ok": "[✓]", "warn": "[!]", "err": "[✗]"}.get(level, "[?]")
    print(f"{ts} {prefix} {msg}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# YAML loaders
# --------------------------------------------------------------------------- #
def load_sources_yaml() -> dict[str, Any]:
    path = DATA_DIR / "sources.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_discography() -> dict[str, Any]:
    path = DATA_DIR / "discography.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# --------------------------------------------------------------------------- #
# DB session
# --------------------------------------------------------------------------- #
@contextmanager
def get_session() -> Iterable[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Texto / detección de menciones
# --------------------------------------------------------------------------- #
def normalize(s: str) -> str:
    """Lower-case + strip acentos + colapsa espacios. Para matching, no para mostrar."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def clean_text(s: str | None) -> str | None:
    if s is None:
        return None
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)  # strip HTML tags si quedan
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def find_referenced_titles(text: str, all_titles: list[tuple[int, str]]) -> list[int]:
    """Devuelve los song_ids cuyos títulos aparecen mencionados en `text`.

    Busca matching con normalización (case-insensitive, sin acentos).
    `all_titles` es una lista de tuples (song_id, title).
    """
    if not text:
        return []
    norm_text = normalize(text)
    matches: list[int] = []
    for song_id, title in all_titles:
        norm_title = normalize(title)
        # Evita matches en títulos demasiado cortos (1-2 palabras genéricas
        # como "Ama" o "Tú" matchean en cualquier texto). Solo títulos
        # con ≥4 caracteres significativos.
        if len(norm_title) < 4:
            continue
        # Usamos regex con word boundaries simulados (espacios o puntuación).
        # No usamos \b porque los títulos pueden tener tildes.
        pattern = r"(^|[^a-z0-9])" + re.escape(norm_title) + r"([^a-z0-9]|$)"
        if re.search(pattern, norm_text):
            matches.append(song_id)
    return matches


# --------------------------------------------------------------------------- #
# Upsert
# --------------------------------------------------------------------------- #
def upsert_source(
    db: Session,
    *,
    kind: str,
    url: str,
    title: str | None = None,
    author: str | None = None,
    published_at: datetime | None = None,
    content_raw: str | None = None,
    content_clean: str | None = None,
    referenced_song_ids: list[int] | None = None,
    quality_score: float | None = None,
) -> int:
    """Inserta una InterpretationSource o actualiza si (kind,url) ya existe.
    Devuelve el id."""
    stmt = (
        pg_insert(InterpretationSource)
        .values(
            kind=kind,
            url=url,
            title=title,
            author=author,
            published_at=published_at,
            content_raw=content_raw,
            content_clean=content_clean,
            referenced_song_ids=referenced_song_ids,
            quality_score=quality_score,
            fetched_at=datetime.now(timezone.utc),
        )
        .on_conflict_do_update(
            constraint="uq_interp_sources_kind_url",
            set_={
                "title": title,
                "author": author,
                "published_at": published_at,
                "content_raw": content_raw,
                "content_clean": content_clean,
                "referenced_song_ids": referenced_song_ids,
                "quality_score": quality_score,
                "fetched_at": datetime.now(timezone.utc),
            },
        )
        .returning(InterpretationSource.id)
    )
    result = db.execute(stmt).scalar_one()
    return int(result)


def get_all_song_titles(db: Session) -> list[tuple[int, str]]:
    """Devuelve [(song_id, title), ...] para detección de menciones."""
    return [(s.id, s.title) for s in db.query(Song).all()]


# --------------------------------------------------------------------------- #
# Retry helper para requests externos
# --------------------------------------------------------------------------- #
http_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)


def polite_sleep(seconds: float = 1.0) -> None:
    """Sleep cooperativo, registrando el motivo para auditoría."""
    time.sleep(seconds)
