"""Imagen de disco para ilustrar un post sobre ese disco (aniversarios,
efemérides musicales, "canción del día", reseñas…).

Fuentes (todas arte oficial del propio disco → uso editorial de riesgo mínimo):
  - La portada auto-alojada en la web (`/album-covers/<slug>.jpg`).
  - Imágenes adicionales (contraportada, libreto, disco…) recogidas de Cover
    Art Archive por `scripts/instagram/fetch_album_media.py` en
    `data/album_media.json`.

Para dar variedad, entre posts distintos sobre el mismo disco se rota la imagen
de forma determinista por tema.
"""
from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Album
from app.services.instagram import config

logger = logging.getLogger(__name__)

_MEDIA_PATH = Path("/app/data/album_media.json")
_media_cache: dict[str, list[dict]] | None = None


def _norm(s: str) -> str:
    """Minúsculas sin acentos, espacios colapsados (matching robusto)."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def _load_media() -> dict[str, list[dict]]:
    """Carga (cacheada) las imágenes adicionales por slug. {} si no existe."""
    global _media_cache
    if _media_cache is None:
        try:
            _media_cache = json.loads(_MEDIA_PATH.read_text())
        except Exception:  # noqa: BLE001 — fichero ausente o ilegible
            _media_cache = {}
    return _media_cache


def find(db: Session, topic: dict) -> dict | None:
    """Si el tema menciona un disco de la discografía, devuelve {'url','kind'}.

    Elige el título más largo que aparezca en el texto (el más específico) y
    rota entre la portada y las imágenes adicionales de ese disco.
    """
    text = _norm(f"{topic.get('title', '')} {topic.get('summary', '')} "
                 f"{topic.get('headline', '')}")
    if not text:
        return None
    rows = db.execute(select(Album.title, Album.slug, Album.cover_url)).all()
    best = None  # (titulo_norm, slug, cover_url)
    for title, slug, cover in rows:
        nt = _norm(title)
        if len(nt) >= 5 and nt in text and (best is None or len(nt) > len(best[0])):
            best = (nt, slug, cover)
    if best is None:
        return None

    _, slug, cover = best
    candidatos: list[str] = []
    if cover:
        url = config.SITE_URL + cover if cover.startswith("/") else cover
        candidatos.append(url)
    # Solo imágenes visualmente fuertes (portada propia + contraportada/libreto);
    # se descartan disco (Medium, redondo/recargado), tray, matrix/runout y la
    # "Front" de CAA (redundante con la portada auto-alojada).
    _UTILES = ("back", "booklet")
    for media in _load_media().get(slug, []):
        t = (media.get("type") or "").lower()
        if media.get("url") and any(u in t for u in _UTILES):
            candidatos.append(media["url"])
    # Dedup preservando orden.
    candidatos = list(dict.fromkeys(candidatos))
    if not candidatos:
        return None

    seed = int(hashlib.md5(
        (topic.get("title") or slug).encode()).hexdigest(), 16)
    idx = seed % len(candidatos)
    elegido = candidatos[idx]
    # La portada frontal (índice 0) lleva tratamiento suave; las imágenes
    # adicionales (contra, libreto, disco) van más oscuras para que el texto
    # se lea sobre arte más recargado.
    kind = "cover" if idx == 0 else "photo"
    logger.info("[cover] disco «%s» (%d imágenes, idx=%d) -> %s",
                slug, len(candidatos), idx, elegido)
    return {"url": elegido, "kind": kind}
