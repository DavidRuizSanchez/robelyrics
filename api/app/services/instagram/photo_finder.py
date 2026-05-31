"""Busca una foto REAL con licencia libre (CC) del protagonista de la noticia.

Fuentes:
  - Wikimedia Commons (CC BY / CC BY-SA / CC0 / dominio público).
  - Openverse (agrega Flickr-CC, museos, etc. — mismas licencias de reúso).

La búsqueda se hace por la ENTIDAD protagonista del tema (`image_query`, que
genera `editorial`: una persona, un lugar, un grupo…), no solo "Extremoduro".
Así cada post lleva la foto de su protagonista real. Si no hay nada con
licencia válida, devuelve None y el post cae a arte IA (degradación elegante).

Solo se aceptan licencias que permiten el reúso con atribución; la atribución
al autor es obligatoria y se incluye en el caption.
"""
from __future__ import annotations

import hashlib
import html
import logging
import re

import httpx

logger = logging.getLogger(__name__)

_WM_API = "https://commons.wikimedia.org/w/api.php"
_OV_API = "https://api.openverse.org/v1/images/"
_UA = (
    "EntreInteriores/1.0 (https://entreinteriores.com; "
    "reparto cultural Robe/Extremoduro)"
)

# Prefijos de licencia que permiten reúso con atribución.
_LICENCIAS_OK = ("cc-by", "cc0", "cc-zero", "pd", "public domain")


def _texto_plano(valor: str) -> str:
    """Limpia HTML y ruido de los metadatos de autor."""
    if not valor:
        return ""
    txt = html.unescape(re.sub(r"<[^>]+>", " ", valor))
    txt = re.sub(r"\s+", " ", txt).strip()
    if "derivative work:" in txt.lower():
        txt = re.split(r"derivative work:", txt, flags=re.IGNORECASE)[-1].strip()
    txt = re.sub(r"\(\s*(web|talk|user|page)\s*\)", "", txt, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", txt).strip()[:70].strip(" :·-")


def _wikimedia(query: str, limit: int = 20) -> list[dict]:
    """Candidatos de Wikimedia Commons con licencia válida (orden por relevancia)."""
    try:
        with httpx.Client(timeout=20.0, headers={"User-Agent": _UA}) as client:
            resp = client.get(_WM_API, params={
                "action": "query", "format": "json",
                "generator": "search",
                "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6,
                "gsrlimit": limit,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata|mime|size",
                "iiurlwidth": 1080,
            })
            resp.raise_for_status()
            pages = resp.json().get("query", {}).get("pages", {})
    except Exception as exc:  # noqa: BLE001
        logger.warning("[foto] Wikimedia falló para %r (%s)", query, exc)
        return []

    # `index` preserva el orden de relevancia del buscador.
    out = []
    for page in sorted(pages.values(), key=lambda p: p.get("index", 999)):
        info = (page.get("imageinfo") or [{}])[0]
        mime = info.get("mime", "")
        if not mime.startswith("image/") or mime in ("image/svg+xml", "image/gif"):
            continue
        if info.get("width", 0) < 600 or info.get("height", 0) < 600:
            continue
        extmeta = info.get("extmetadata", {})
        if "NonFree" in extmeta:
            continue
        lic = (extmeta.get("License", {}).get("value", "") or "").lower()
        if not (lic and any(lic.startswith(p) for p in _LICENCIAS_OK)):
            continue
        autor = _texto_plano(extmeta.get("Artist", {}).get("value", "")) or "Autor desconocido"
        licencia = _texto_plano(extmeta.get("LicenseShortName", {}).get("value", "")) or "CC"
        out.append({
            "url": info.get("thumburl") or info.get("url"),
            "credit": f"{autor} · Wikimedia Commons ({licencia})",
        })
    return out


def _openverse(query: str, limit: int = 20) -> list[dict]:
    """Candidatos de Openverse (Flickr-CC y otros), licencias de reúso."""
    try:
        with httpx.Client(timeout=20.0, headers={"User-Agent": _UA}) as client:
            resp = client.get(_OV_API, params={
                "q": query,
                "license_type": "commercial,modification",
                "page_size": limit,
                "mature": "false",
            })
            resp.raise_for_status()
            results = resp.json().get("results", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("[foto] Openverse falló para %r (%s)", query, exc)
        return []

    out = []
    for it in results:
        url = it.get("url")
        if not url or (it.get("width", 0) and it["width"] < 600):
            continue
        creator = (it.get("creator") or "Autor desconocido").strip()[:70]
        lic = " ".join(p for p in ["CC", (it.get("license") or "").upper(),
                                   it.get("license_version") or ""] if p).strip()
        src = (it.get("source") or "Openverse").strip()
        out.append({"url": url, "credit": f"{creator} · {src} ({lic})"})
    return out


def _queries(topic: dict) -> list[str]:
    """Consultas de la más específica (entidad) a la genérica."""
    qs = []
    iq = (topic.get("image_query") or "").strip()
    if iq:
        qs.append(iq)
    # Respaldo genérico solo si no había entidad fiable.
    qs.append("Extremoduro Robe Iniesta concierto")
    # Dedup preservando orden.
    return list(dict.fromkeys(q for q in qs if q))


def find(topic: dict) -> dict | None:
    """Devuelve {'url','credit'} de una foto CC del protagonista, o None.

    Para cada consulta combina Wikimedia + Openverse y elige entre las primeras
    (más relevantes) de forma determinista por tema: estable para el mismo tema,
    variada entre temas distintos.
    """
    for query in _queries(topic):
        candidatos = (_wikimedia(query) + _openverse(query))[:8]
        if candidatos:
            seed = int(hashlib.md5(
                (topic.get("title") or query).encode()).hexdigest(), 16)
            elegido = candidatos[seed % len(candidatos)]
            logger.info("[foto] «%s» -> %s", query, elegido["credit"])
            return {"url": elegido["url"], "credit": elegido["credit"]}
    logger.info("[foto] sin fotos CC; se usará arte IA.")
    return None
