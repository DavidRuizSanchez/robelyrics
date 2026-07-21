"""Loader de los YAML curados de verdad de base (letras, autoría, catálogo).

Estos ficheros viven en `data/` (montado read-only en prod: la escritura de
correcciones va a BD con proveniencia; el YAML es la semilla versionada en git).
Cada entrada lleva `source` y `status`:
  - status: verified            → verdad confirmada; se aplica directa.
  - status: pending_verification → candidata; el Motor de Consenso la corrobora
    contra fuentes reales antes de aplicar. NUNCA se aplica sin corroborar.

Uso: los verificadores por eje leen los `pending_verification` como pistas de
qué revisar; los seeders aplican los `verified`.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _load_yaml(name: str) -> dict[str, Any]:
    try:
        import yaml

        p = _DATA_DIR / name
        if not p.exists():
            return {}
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # nunca romper por un YAML mal formado
        logger.warning("[curated_overrides] no se pudo leer %s: %s", name, exc)
        return {}


@lru_cache(maxsize=1)
def lyric_overrides() -> list[dict]:
    """Correcciones de letra. Cada dict: album_slug, song_title, status, source,
    reason, line_fixes?, full_lyrics?, continues_with?."""
    return list(_load_yaml("lyric_overrides.yaml").get("overrides") or [])


@lru_cache(maxsize=1)
def song_credits() -> list[dict]:
    """Créditos de autoría. Cada dict: song_title, album_slug?, status, source,
    credits: [{role, name, person_slug?, primary?, note?}]."""
    return list(_load_yaml("song_credits.yaml").get("credits") or [])


@lru_cache(maxsize=1)
def canonical_tracklists() -> list[dict]:
    """Primera aparición canónica. Cada dict: song_title, original_album,
    original_album_slug, original_year, status, source, note?."""
    return list(_load_yaml("tracklists.yaml").get("canonical") or [])


def verified_only(entries: list[dict]) -> list[dict]:
    return [e for e in entries if (e.get("status") or "").lower() == "verified"]


def pending_only(entries: list[dict]) -> list[dict]:
    return [e for e in entries if (e.get("status") or "").lower() == "pending_verification"]
