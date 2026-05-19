"""Búsqueda de imágenes libres en Wikimedia Commons.

Uso típico (en scripts de generación de posts/personas):

    from app.services.wikimedia import search_image
    img = search_image("Robe Iniesta")
    if img:
        post.hero_image_url = img.thumb_url
        post.hero_image_attribution = img.attribution_text
        post.hero_image_license = img.license_short
        post.hero_image_source_url = img.source_page_url

API pública de Commons, sin auth. Requiere User-Agent identificable según la
política de Wikimedia. Solo se aceptan licencias libres (CC0, CC-BY*, CC-BY-SA*,
Public Domain); el resto se filtra. NO descargamos los ficheros — hot-link
directo desde upload.wikimedia.org (permitido por su política).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

API_ENDPOINT = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = (
    "RobeLyrics/1.0 (https://entreinteriores.com; "
    "davidruizsanchez@gmail.com) httpx"
)

# Licencias aceptadas. Se comparan en lowercase contra el campo
# `extmetadata.License.value` que devuelve Commons (e.g. "cc-by-sa-4.0").
ALLOWED_LICENSE_PREFIXES = (
    "cc0",
    "cc-by-",
    "cc-by-sa-",
    "pdm",
    "pd-",
)
ALLOWED_LICENSE_EXACT = {"public domain", "pd", "no restrictions"}

# Tamaño mínimo aceptable para una imagen heroica.
MIN_WIDTH = 600

# Mime types soportados. Excluimos SVG y TIFF para que el navegador no se
# atragante en posts editoriales.
ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp"}


@dataclass(frozen=True)
class WikimediaImage:
    title: str
    url: str               # URL canónica del fichero original
    thumb_url: str         # Thumbnail dimensionado (≤ 1200px width)
    width: int
    height: int
    license_short: str     # ej. "CC BY-SA 4.0"
    license_url: str | None
    author: str            # ya limpio de HTML
    source_page_url: str   # File: page en Commons (para atribución)

    @property
    def attribution_text(self) -> str:
        """Línea Markdown lista para pegar en el footer del post."""
        author = self.author or "autor desconocido"
        license_part = self.license_short or "licencia libre"
        return (
            f"*Foto: {author} — {license_part} — "
            f"vía [Wikimedia Commons]({self.source_page_url})*"
        )


# --------------------------------------------------------------------------- #
# Helpers de licencia y autor
# --------------------------------------------------------------------------- #
def _license_allowed(license_value: str | None) -> bool:
    if not license_value:
        return False
    v = license_value.strip().lower()
    if v in ALLOWED_LICENSE_EXACT:
        return True
    return any(v.startswith(p) for p in ALLOWED_LICENSE_PREFIXES)


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = _HTML_TAG_RE.sub(" ", value)
    text = text.replace("&amp;", "&").replace("&nbsp;", " ")
    return _WHITESPACE_RE.sub(" ", text).strip()


# --------------------------------------------------------------------------- #
# Búsqueda
# --------------------------------------------------------------------------- #
def search_image(
    query: str,
    *,
    limit: int = 10,
    thumb_width: int = 1200,
    timeout: float = 10.0,
) -> WikimediaImage | None:
    """Busca una imagen libre en Commons que matchee `query`.

    Devuelve la primera con licencia permitida y dimensiones suficientes, o
    None si no encuentra ninguna válida.
    """
    if not query or not query.strip():
        return None

    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": "6",  # File:
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime|size|user",
        "iiurlwidth": str(thumb_width),
    }
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    try:
        with httpx.Client(timeout=timeout, headers=headers) as client:
            resp = client.get(API_ENDPOINT, params=params)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Wikimedia search failed for %r: %s", query, exc)
        return None

    pages = data.get("query", {}).get("pages", [])
    if not isinstance(pages, list):
        # formatversion 1 devuelve dict; defensivo
        pages = list(pages.values()) if isinstance(pages, dict) else []

    for page in pages:
        info_list = page.get("imageinfo") or []
        if not info_list:
            continue
        info = info_list[0]
        mime = info.get("mime")
        if mime not in ALLOWED_MIMES:
            continue
        width = info.get("width") or 0
        if width < MIN_WIDTH:
            continue
        meta = info.get("extmetadata") or {}
        license_value = (meta.get("License") or {}).get("value")
        if not _license_allowed(license_value):
            continue

        title = page.get("title", "")
        source_page = f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}"
        author_raw = (meta.get("Artist") or {}).get("value") or (
            (meta.get("Credit") or {}).get("value") or ""
        )
        return WikimediaImage(
            title=title,
            url=info.get("url", ""),
            thumb_url=info.get("thumburl") or info.get("url", ""),
            width=width,
            height=info.get("height") or 0,
            license_short=(meta.get("LicenseShortName") or {}).get("value")
            or license_value,
            license_url=(meta.get("LicenseUrl") or {}).get("value"),
            author=_strip_html(author_raw),
            source_page_url=source_page,
        )

    return None
