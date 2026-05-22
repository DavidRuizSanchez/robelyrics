"""Busca una foto real con licencia libre para ilustrar una noticia.

Fuente: Wikimedia Commons. SOLO se aceptan imágenes con licencia que permite
el reúso (Creative Commons CC BY / CC BY-SA, CC0 o dominio público); en esas
licencias la atribución del autor es obligatoria y suficiente.

Si no se encuentra ninguna foto válida, se devuelve None y el post usa el
fondo IA abstracto de siempre (degradación elegante).
"""
from __future__ import annotations

import hashlib
import html
import logging
import re

import httpx

logger = logging.getLogger(__name__)

_API = "https://commons.wikimedia.org/w/api.php"
_UA = (
    "EntreInteriores/1.0 (https://entreinteriores.com; "
    "reparto cultural Robe/Extremoduro)"
)

# Prefijos de licencia que permiten reúso con atribución.
_LICENCIAS_OK = ("cc-by", "cc0", "cc-zero", "pd", "public domain")


def _texto_plano(valor: str) -> str:
    """Limpia el HTML y el ruido de los metadatos de autor de Wikimedia."""
    if not valor:
        return ""
    txt = html.unescape(re.sub(r"<[^>]+>", " ", valor))
    txt = re.sub(r"\s+", " ", txt).strip()
    # En obras derivadas, el autor a atribuir es el de la derivada.
    if "derivative work:" in txt.lower():
        txt = re.split(r"derivative work:", txt, flags=re.IGNORECASE)[-1].strip()
    txt = re.sub(r"\(\s*(web|talk|user|page)\s*\)", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt[:70].strip(" :·-")


def _licencia_valida(extmeta: dict) -> bool:
    if "NonFree" in extmeta:
        return False
    lic = (extmeta.get("License", {}).get("value", "") or "").lower()
    return bool(lic) and any(lic.startswith(p) for p in _LICENCIAS_OK)


def _consultar(query: str, tokens: tuple, limit: int = 16) -> list[dict]:
    """Consulta Wikimedia Commons y devuelve candidatos con licencia válida.

    `tokens` son palabras que DEBEN aparecer en el título del archivo: filtro
    de relevancia que evita falsos positivos (p.ej. el pueblo «Robe» de
    Australia al buscar «Robe Iniesta»).
    """
    try:
        with httpx.Client(timeout=20.0, headers={"User-Agent": _UA}) as client:
            resp = client.get(_API, params={
                "action": "query", "format": "json",
                "generator": "search",
                "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": limit,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata|mime|size",
                "iiurlwidth": 1080,
            })
            resp.raise_for_status()
            pages = resp.json().get("query", {}).get("pages", {})
    except Exception as exc:  # noqa: BLE001
        logger.warning("[foto] búsqueda en Wikimedia falló (%s).", exc)
        return []

    candidatos = []
    for page in pages.values():
        titulo = (page.get("title", "") or "").lower()
        if tokens and not any(tok in titulo for tok in tokens):
            continue
        info = (page.get("imageinfo") or [{}])[0]
        if not info.get("mime", "").startswith("image/"):
            continue
        if info.get("mime") in ("image/svg+xml", "image/gif"):
            continue
        if info.get("width", 0) < 600 or info.get("height", 0) < 600:
            continue
        extmeta = info.get("extmetadata", {})
        if not _licencia_valida(extmeta):
            continue
        autor = (
            _texto_plano(extmeta.get("Artist", {}).get("value", ""))
            or "Autor desconocido"
        )
        licencia = (
            _texto_plano(extmeta.get("LicenseShortName", {}).get("value", ""))
            or "CC"
        )
        candidatos.append({
            "url": info.get("thumburl") or info.get("url"),
            "credit": f"{autor} · Wikimedia Commons ({licencia})",
            "page": page.get("title", ""),
        })
    return candidatos


def _busquedas(topic: dict) -> list[tuple]:
    """Lista de (gsrsearch, tokens_obligatorios), de más específica a genérica."""
    title = (topic.get("title") or "").lower()
    bs = []
    if "iñaki" in title or "uoho" in title:
        bs.append(('intitle:Extremoduro Antón', ("extremoduro",)))
    if "robe" in title:
        bs.append(('intitle:"Robe Iniesta"', ("robe iniesta",)))
    # Respaldo fiable: fotos del grupo (acotadas por título).
    bs.append(("intitle:Extremoduro", ("extremoduro",)))
    return bs


def find(topic: dict) -> dict | None:
    """Devuelve {'url', 'credit'} de una foto con licencia, o None.

    La elección es determinista por tema (estable para el mismo tema, varía
    entre temas) para no repetir siempre la misma foto.
    """
    for query, tokens in _busquedas(topic):
        candidatos = _consultar(query, tokens)
        if candidatos:
            seed = int(
                hashlib.md5((topic.get("title") or "").encode()).hexdigest(), 16
            )
            elegido = candidatos[seed % len(candidatos)]
            logger.info(
                "[foto] Wikimedia: «%s» — %s", elegido["page"], elegido["credit"]
            )
            return {"url": elegido["url"], "credit": elegido["credit"]}
    logger.info("[foto] sin fotos con licencia; se usará fondo IA abstracto.")
    return None
