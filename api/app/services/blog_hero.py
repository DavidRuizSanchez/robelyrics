"""Hero image ÚNICO por post — nunca se repite una imagen entre posts.

Estrategia (decisión de producto): primero una imagen REAL de la entidad
protagonista aún NO usada por otro post/propuesta; si todas están ya usadas, se
genera arte editorial ÚNICO con gpt-image-1 (estilo "Entre Interiores", granate
sobre negro) y se sube a Cloudinary. Siempre se devuelve un ALT descriptivo de la
imagen real (no del título del post) para accesibilidad + SEO.

Regla dura del proyecto: JAMÁS dos posts con la misma foto.
"""
from __future__ import annotations

import contextlib
import logging
import os
import tempfile
import zlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.hero_image import pick_hero_image

logger = logging.getLogger(__name__)


def used_hero_urls(db: Session) -> set[str]:
    """URLs de imagen hero ya empleadas por cualquier Post o ContentProposal."""
    from app.db.models import ContentProposal, Post

    urls: set[str] = set()
    for (u,) in db.execute(select(Post.hero_image_url).where(Post.hero_image_url.isnot(None))):
        urls.add(u)
    for (u,) in db.execute(
        select(ContentProposal.hero_image_url).where(ContentProposal.hero_image_url.isnot(None))
    ):
        urls.add(u)
    return urls


def _seed(subject: str) -> int:
    """Semilla estable (sin aleatoriedad) para variar el estilo del arte IA."""
    return zlib.crc32((subject or "entre interiores").encode("utf-8"))


def _ai_hero(subject: str, seed: int) -> dict | None:
    """Arte editorial ÚNICO con gpt-image-1 subido a Cloudinary. None si no hay
    API key o falla (el caller degrada a sin-imagen, nunca a una repetida)."""
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    path = None
    try:
        from app.services.instagram import cloudinary_upload, imaging

        img = imaging._ai_background(subject or "Robe y Extremoduro", seed)
        img = imaging._treat(img, has_photo=False)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as fh:
            path = fh.name
        img.convert("RGB").save(path, "JPEG", quality=90)
        url = cloudinary_upload.upload(path, folder="entreinteriores-blog")
        return {
            "url": url, "attribution": None, "license": None, "source": None,
            "alt": f"Ilustración editorial que evoca «{subject}»",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("arte IA de hero falló (%s): %s", subject, exc)
        return None
    finally:
        if path and os.path.exists(path):
            with contextlib.suppress(OSError):
                os.unlink(path)


def build_unique_hero(
    db: Session,
    entities: list[dict] | None,
    subject: str,
    *,
    allow_ai: bool = True,
    used: set[str] | None = None,
) -> dict | None:
    """Devuelve {url, alt, attribution, license, source} ÚNICO para el post, o None.

    1) Imagen REAL de la entidad no usada aún (dedup duro).
    2) Si no hay ninguna libre → arte editorial IA único (si `allow_ai`).
    """
    used = used if used is not None else used_hero_urls(db)
    img = pick_hero_image(db, entities, used=used)
    if img:
        return img
    if allow_ai:
        ai = _ai_hero(subject, _seed(subject))
        # El arte IA es único por definición, pero por si acaso comprobamos.
        if ai and ai["url"] not in used:
            return ai
    return None
