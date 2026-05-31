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

from app.services import wikimedia

logger = logging.getLogger(__name__)

_WM_API = "https://commons.wikimedia.org/w/api.php"
_OV_API = "https://api.openverse.org/v1/images/"
_WD_API = "https://www.wikidata.org/w/api.php"
_UA = (
    "EntreInteriores/1.0 (https://entreinteriores.com; "
    "reparto cultural Robe/Extremoduro)"
)

# Prefijos de licencia que permiten reúso con atribución.
_LICENCIAS_OK = ("cc-by", "cc0", "cc-zero", "pd", "public domain")

# Pistas de descripción para desambiguar entidades del dominio (música/cultura)
# frente a homónimos (municipios, apellidos…) al buscar en Wikidata.
_DOMINIO_HINTS = (
    "sing", "music", "músic", "musico", "cantante", "banda", "band", "grupo",
    "guitar", "bater", "rock", "composit", "artist", "dj", "rapero", "rapper",
    "poeta", "escritor", "writer", "actor", "actriz", "director",
)


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


def _p18_filename(qid: str) -> str | None:
    """Nombre del fichero de la imagen (propiedad P18) de una entidad Wikidata."""
    try:
        with httpx.Client(timeout=20.0, headers={"User-Agent": _UA}) as client:
            resp = client.get(_WD_API, params={
                "action": "wbgetclaims", "entity": qid,
                "property": "P18", "format": "json",
            })
            resp.raise_for_status()
            claims = resp.json().get("claims", {}).get("P18", [])
        return claims[0]["mainsnak"]["datavalue"]["value"] if claims else None
    except Exception:  # noqa: BLE001
        return None


def _wikidata_photo(query: str) -> dict | None:
    """Foto canónica de la ENTIDAD vía Wikidata (P18) → Commons.

    Es la fuente más precisa: cada protagonista (persona, lugar, grupo) recibe
    SU foto, no una genérica. Desambigua homónimos priorizando entidades cuya
    descripción encaja con el dominio (música/cultura).
    """
    try:
        with httpx.Client(timeout=20.0, headers={"User-Agent": _UA}) as client:
            resp = client.get(_WD_API, params={
                "action": "wbsearchentities", "search": query,
                "language": "es", "uselang": "es", "format": "json",
                "limit": 7, "type": "item",
            })
            resp.raise_for_status()
            cands = resp.json().get("search", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("[foto] Wikidata falló para %r (%s)", query, exc)
        return None
    cands.sort(key=lambda c: 0 if any(
        h in (c.get("description") or "").lower() for h in _DOMINIO_HINTS
    ) else 1)
    for c in cands:
        filename = _p18_filename(c["id"])
        if not filename:
            continue
        wimg = wikimedia.get_file_info(filename)
        if wimg and wimg.thumb_url:
            credit = (f"{wimg.author or 'Autor desconocido'} · "
                      f"Wikimedia Commons ({wimg.license_short or 'CC'})")
            logger.info("[foto] Wikidata %s «%s» -> %s",
                        c["id"], c.get("label"), credit)
            return {"url": wimg.thumb_url, "credit": credit}
    return None


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

    Orden de fuentes:
      1. Wikidata P18 por la entidad de `image_query` (la foto canónica del
         protagonista; máxima precisión y variedad).
      2. Wikimedia + Openverse por texto (respaldo).
    """
    iq = (topic.get("image_query") or "").strip()
    if iq:
        wd = _wikidata_photo(iq)
        if wd:
            return wd

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
