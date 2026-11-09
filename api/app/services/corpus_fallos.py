"""Por qué no se pudo transcribir un vídeo, y si tiene arreglo.

La pregunta que decide no es «¿lo arreglaría reintentar?», sino «¿lo puede
arreglar una acción nuestra?» (criterio del asesor, 09-11-2026):

- **permanente**: no (restricción de edad, porque no se usan cookies; un vídeo
  casi sin habla; privado o borrado). Agotados los intentos pasa a `abandoned`.
- **extractor**: yt-dlp revienta por dentro. Se arregla actualizando yt-dlp, y
  YouTube lo rompe cada pocas semanas, así que NO gasta intento: queda apuntado
  con la versión que falló y se reintenta solo cuando el daemon trae otra.
- **transitorio**: todo lo demás (red, 5xx, un 502 de un rebuild). Como siempre.

Un error que no se reconoce es transitorio: quema intento y acaba como hoy, en
«Fallidos», a la vista. Clasificar de más como permanente escondería algo.
"""
from __future__ import annotations

import re

_PERMANENTES: tuple[tuple[re.Pattern, str], ...] = tuple(
    (re.compile(p, re.I), motivo) for p, motivo in (
        (r"confirm your age|age[- ]restricted|inappropriate for some users",
         "YouTube pide confirmar la edad, y eso exige cookies, que no se usan"),
        (r"transcripci[oó]n demasiado corta",
         "casi no tiene habla: la transcripción sale demasiado corta"),
        (r"private video|v[ií]deo privado", "el vídeo es privado"),
        (r"video unavailable|this video is no longer available|has been removed|"
         r"account associated with this video has been terminated|HTTP Error 404",
         "el vídeo ya no existe"),
        (r"members[- ]only|join this channel", "es solo para miembros del canal"),
    )
)
_EXTRACTOR = re.compile(
    r"please report this issue|expected string or bytes-like object|unable to extract|"
    r"unsupported url", re.I)
_PREFIJO_EXTRACTOR = "[extractor · yt-dlp "


def clasificar(error: str | None) -> str:
    texto = error or ""
    if any(p.search(texto) for p, _ in _PERMANENTES):
        return "permanente"
    if _EXTRACTOR.search(texto):
        return "extractor"
    return "transitorio"


def motivo(error: str | None) -> str | None:
    """La frase que se enseña en el panel para un vídeo abandonado."""
    texto = error or ""
    for p, m in _PERMANENTES:
        if p.search(texto):
            return m
    if "ivoox" in texto.lower():
        return "iVoox no deja descargar el audio"
    return None


def marca_extractor(version: str) -> str:
    return f"{_PREFIJO_EXTRACTOR}{version}] "


def fallo_con_version(error: str | None, version: str) -> bool:
    """¿Este fallo de extractor es de ESTA versión de yt-dlp? Entonces no se reintenta."""
    return (error or "").startswith(marca_extractor(version))
