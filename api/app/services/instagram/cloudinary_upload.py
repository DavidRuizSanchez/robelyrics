"""Sube imágenes a Cloudinary para obtener una URL pública.

La Graph API de Instagram exige una `image_url` accesible públicamente; no
acepta ficheros locales. Cloudinary (plan gratuito) cumple esa función.
"""
from __future__ import annotations

import cloudinary
import cloudinary.uploader

from app.services.instagram import config

_configured = False


def _ensure() -> None:
    global _configured
    if not _configured:
        cloudinary.config(
            cloud_name=config.CLOUDINARY_CLOUD_NAME,
            api_key=config.CLOUDINARY_API_KEY,
            api_secret=config.CLOUDINARY_API_SECRET,
            secure=True,
        )
        _configured = True


def upload(image_path: str, folder: str = "entreinteriores-ig") -> str:
    """Sube una imagen y devuelve su URL pública (secure_url)."""
    _ensure()
    result = cloudinary.uploader.upload(
        image_path,
        folder=folder,
        resource_type="image",
    )
    return result["secure_url"]
