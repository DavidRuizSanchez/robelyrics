"""Licencia de una imagen para su `ImageObject`, cuando la hay que declarar.

GSC (20-11-2026) avisaba en 7 posts de que faltan `license`, `creator`,
`copyrightNotice` y `acquireLicensePage`: solo se servía `creditText`. Los datos
estaban en `posts.hero_image_license`, `hero_image_source_url` y en el propio crédito.

Solo se declara una licencia Creative Commons que conste escrita (en el campo o en el
crédito). Una portada de disco, un cartel o una foto de prensa no tienen licencia que
declarar: se quedan con su `creditText` y Google mantiene el aviso, que es lo correcto.
Puro: lo prueban los tests con los créditos reales de producción.
"""
from __future__ import annotations

import re
from urllib.parse import unquote

_CC = re.compile(r"\bCC[ -](BY(?:-NC)?(?:-SA|-ND)?)[ -](\d\.\d)\b", re.I)
_ENLACE_MD = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_FILE_COMMONS = re.compile(r"https://commons\.wikimedia\.org/wiki/File:[^\s)\"']+")
_SUBIDA_COMMONS = re.compile(
    r"https://upload\.wikimedia\.org/wikipedia/commons/(?:thumb/)?[0-9a-f]/[0-9a-f]{2}/([^/]+)")
_FICHERO_ORIGEN = re.compile(r"^File:.*?\.(?:jpe?g|png|gif|tiff?|webp)\s*:\s*", re.I)
_URL = re.compile(r"https?://\S+")


def licencia_cc(*textos: str | None) -> tuple[str, str] | None:
    """(«CC BY-SA 4.0», URL canónica) de la primera licencia CC escrita con su versión."""
    for t in textos:
        m = _CC.search(t or "")
        if m:
            clave, version = m.group(1).upper(), m.group(2)
            return (f"CC {clave} {version}",
                    f"https://creativecommons.org/licenses/{clave.lower()}/{version}/")
    return None


def autores(credito: str | None) -> list[str]:
    """Los autores que nombra un crédito, sin el resto (licencia, «vía Wikimedia»…).

    Formas reales: «*Foto: Ruben Ortega · CC BY-SA 2.0 · vía [Wikimedia Commons](…)*»,
    «elchicogris · Wikimedia Commons (CC BY-SA 2.0)» y la de una obra derivada,
    «File:X.jpg : Ruben Ortega derivative work: Alonso de Mendoza».
    """
    t = _ENLACE_MD.sub(r"\1", (credito or "").strip().strip("*").strip())
    t = re.sub(r"^Foto:\s*", "", t, flags=re.I)
    primero = t.split(" · ")[0].strip()
    primero = _URL.sub("", _FICHERO_ORIGEN.sub("", primero)).strip()
    partes = re.split(r"\s*derivative work:\s*", primero, flags=re.I)
    return [p.strip(" :;,") for p in partes if p.strip(" :;,")]


def pagina_de_commons(*textos: str | None) -> str | None:
    """La página `File:` de Commons de la imagen: tal cual, o deducida de la URL del
    fichero subido (también de una miniatura)."""
    for t in textos:
        m = _FILE_COMMONS.search(t or "")
        if m:
            return m.group(0)
    for t in textos:
        m = _SUBIDA_COMMONS.search(t or "")
        if m:
            return f"https://commons.wikimedia.org/wiki/File:{unquote(m.group(1))}"
    return None


def derechos_de_imagen(credito: str | None, licencia: str | None,
                       url_fuente: str | None) -> dict | None:
    """Lo que el `ImageObject` puede declarar, o None si no hay licencia CC escrita."""
    cc = licencia_cc(licencia, credito)
    if not cc:
        return None
    nombre, url = cc
    out: dict = {"license_name": nombre, "license_url": url}
    quienes = autores(credito)
    if quienes:
        out["creators"] = quienes
        out["copyright_notice"] = f"© {', '.join(quienes)} ({nombre})"
    pagina = pagina_de_commons(url_fuente, credito)
    if pagina:
        out["acquire_license_page"] = pagina
    return out
