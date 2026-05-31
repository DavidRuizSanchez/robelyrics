"""Encuentra la portada de un disco de Robe/Extremoduro para ilustrar un post
que trate sobre ese disco (aniversarios, efemérides musicales, "canción del
día", reseñas…).

Las portadas están auto-alojadas en la web (`/album-covers/<slug>.jpg`).
Usar la portada de un disco para hablar de ese mismo disco es uso editorial
normalizado y de riesgo mínimo (lo hacen Spotify, prensa, etc.), a diferencia
de republicar fotos de prensa con copyright.
"""
from __future__ import annotations

import logging
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Album
from app.services.instagram import config

logger = logging.getLogger(__name__)


def _norm(s: str) -> str:
    """Minúsculas sin acentos, espacios colapsados (para matching robusto)."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def find(db: Session, topic: dict) -> dict | None:
    """Si el tema menciona un disco de la discografía, devuelve {'url','kind'}.

    Elige el título más largo que aparezca en el texto (el más específico).
    """
    text = _norm(f"{topic.get('title', '')} {topic.get('summary', '')} "
                 f"{topic.get('headline', '')}")
    if not text:
        return None
    rows = db.execute(select(Album.title, Album.cover_url)).all()
    best_title, best_cover = "", None
    for title, cover in rows:
        if not cover:
            continue
        nt = _norm(title)
        # Mínimo 5 chars para evitar matches triviales.
        if len(nt) >= 5 and nt in text and len(nt) > len(best_title):
            best_title, best_cover = nt, cover
    if not best_cover:
        return None
    url = config.SITE_URL + best_cover if best_cover.startswith("/") else best_cover
    logger.info("[cover] disco detectado «%s» -> %s", best_title, url)
    return {"url": url, "kind": "cover"}
