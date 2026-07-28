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


def upload_video(
    video_path: str, folder: str = "entreinteriores-ig-video"
) -> dict:
    """Sube un vídeo. Devuelve {url, public_id, duration, width, height}.

    Se usa `upload_large`, que trocea el envío: los MP4 pasan de los 20 MB con
    facilidad y `upload` a secas falla ahí. Guardar el `public_id` es lo que
    permite luego borrar de Cloudinary lo que quede huérfano.
    """
    _ensure()
    result = cloudinary.uploader.upload_large(
        video_path,
        folder=folder,
        resource_type="video",
        chunk_size=6_000_000,
    )
    return {
        "url": result["secure_url"],
        "public_id": result.get("public_id"),
        "duration": result.get("duration"),
        "width": result.get("width"),
        "height": result.get("height"),
    }


def destroy(public_id: str, resource_type: str = "image") -> bool:
    """Borra un asset de Cloudinary. Para retirar un clip rápido si hace falta.

    `invalidate=True` es imprescindible y no es un detalle: sin él, Cloudinary
    borra el asset pero la copia del CDN sigue sirviéndose desde su URL. Se
    comprobó en la primera prueba de retirada — el fichero ya no existía en la
    cuenta y la URL seguía devolviendo 200.

    La invalidación no es instantánea: Cloudinary la propaga por el CDN en unos
    minutos. Quien llame a esto no debe prometer que el vídeo ya es inaccesible.
    """
    _ensure()
    res = cloudinary.uploader.destroy(
        public_id, resource_type=resource_type, invalidate=True
    )
    return res.get("result") == "ok"
