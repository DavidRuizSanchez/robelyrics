"""Fechas de subida de los vídeos de YouTube: con hora y zona, o no valen.

GSC (20-11-2026) marcaba «Falta el campo uploadDate» en 2 vídeos y «falta la zona
horaria» / «el valor de fecha y hora no es válido» en 18: se servía la fecha sola
(«2018-11-15») porque `news_research` guardaba `publishedAt[:10]` y
`related_videos.upload_date` es `Date`. La hora real está en `snippet.publishedAt` de
la YouTube Data API; nunca se completa con una medianoche inventada.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime

import httpx

_CON_HORA_Y_ZONA = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})$")
_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def tiene_hora_y_zona(texto: str | None) -> bool:
    """¿Es un ISO 8601 con hora y zona horaria, como pide Google en `uploadDate`?"""
    return bool(_CON_HORA_Y_ZONA.match((texto or "").strip()))


def parse_subida(texto: str | None) -> tuple[date | None, datetime | None]:
    """(día, instante) de una fecha de subida. El instante solo si trae hora y zona."""
    t = (texto or "").strip()
    if not t:
        return None, None
    if tiene_hora_y_zona(t):
        instante = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return instante.date(), instante
    try:
        return date.fromisoformat(t[:10]), None
    except ValueError:
        return None, None


def published_at_de_youtube(ids: list[str], *, key: str | None = None,
                            client: httpx.Client | None = None) -> dict[str, str]:
    """`snippet.publishedAt` de cada vídeo (ISO con su `Z`), en tandas de 50 (1 unidad
    de cuota cada una). Un vídeo borrado o privado no vuelve en la respuesta y se queda
    fuera del resultado: no se le inventa fecha. Si la API falla, lanza."""
    key = key or os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise RuntimeError("falta YOUTUBE_API_KEY")
    unicos = list(dict.fromkeys(i for i in ids if i))
    propio = client is None
    c = client or httpx.Client(timeout=30)
    out: dict[str, str] = {}
    try:
        for i in range(0, len(unicos), 50):
            r = c.get(_VIDEOS_URL, params={"part": "snippet", "id": ",".join(unicos[i:i + 50]),
                                           "key": key})
            r.raise_for_status()
            for item in r.json().get("items", []):
                publicado = (item.get("snippet") or {}).get("publishedAt")
                if tiene_hora_y_zona(publicado):
                    out[item["id"]] = publicado
    finally:
        if propio:
            c.close()
    return out
