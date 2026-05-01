"""Singleton del cliente Qdrant para toda la app."""
from __future__ import annotations

from functools import lru_cache

from qdrant_client import QdrantClient

from app.config import get_settings


@lru_cache(maxsize=1)
def get_qdrant() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(url=settings.qdrant_url, check_compatibility=False)
