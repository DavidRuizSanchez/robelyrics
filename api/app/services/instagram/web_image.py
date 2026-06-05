"""Búsqueda de imágenes en la web (Google Images vía DataForSEO).

Para los posts de Instagram el usuario autoriza usar CUALQUIER foto relevante
de internet (no solo CC), priorizando que la imagen sea CORRECTA y del sujeto
real. Esta es la fuente principal de fotos del `photo_finder`; las fuentes CC
(Wikimedia/Openverse) quedan como respaldo.

Devuelve, por candidato:
  - url:   la imagen a tamaño completo (campo `source_url` de DataForSEO).
  - thumb: el thumbnail de Google (`encoded_url`), respaldo fiable si la imagen
           full no se puede descargar (hotlink/404).
  - title: título/alt del resultado (para depurar y para una verificación laxa).

Degradación elegante: si no hay credenciales o la API falla, devuelve [].
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.dataforseo.com/v3/serp/google/images/live/advanced"
_LOCATION_ES = 2724  # España
_LANGUAGE_ES = "es"


def search(query: str, depth: int = 20) -> list[dict]:
    """Busca imágenes en Google Images. Lista ordenada por ranking de Google."""
    query = (query or "").strip()
    if not query:
        return []
    login = os.environ.get("DATAFORSEO_LOGIN")
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if not login or not password:
        logger.info("[web_image] sin credenciales DataForSEO; se omite.")
        return []

    payload = [{
        "keyword": query,
        "location_code": _LOCATION_ES,
        "language_code": _LANGUAGE_ES,
        "depth": depth,
    }]
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(_ENDPOINT, auth=(login, password), json=payload)
            resp.raise_for_status()
            data = resp.json()
        items = data["tasks"][0]["result"][0]["items"] or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("[web_image] búsqueda falló para '%s': %s", query, exc)
        return []

    out: list[dict] = []
    for it in items:
        if it.get("type") != "images_search":
            continue
        src = (it.get("source_url") or "").strip()
        thumb = (it.get("encoded_url") or "").strip()
        if not src and not thumb:
            continue
        out.append({
            "url": src or thumb,
            "thumb": thumb,
            "title": (it.get("title") or it.get("alt") or "").strip(),
        })
    logger.info("[web_image] '%s' -> %d imágenes", query, len(out))
    return out
