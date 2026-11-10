"""Fotos dentro del cuerpo de una ficha (petición de David, 10-11-2026).

Hasta ahora el cuerpo solo podía llevar la foto de OTRA entidad de la BD
(`merge_deep.imagen_para`). En la ficha de un muralista lo que aporta es su mural,
que no es una entidad. Las fotos se declaran en `data/body_images.yaml`, con su
sección, crédito y fuente, y pasan la misma guarda que cualquier foto: re-alojadas
en casa, libres o de terceros con crédito (`image_guard.third_party_credited`), y
con la identidad comprobada en la página de origen.

Se insertan como `![alt](url "crédito")` justo bajo su heading, que es lo que
`MarkdownArticle` pinta como <figure> con pie. Idempotente: si la foto ya está,
no se toca nada; el resto del cuerpo queda igual.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_DATA = Path(__file__).resolve().parents[2] / "data" / "body_images.yaml"


def cargar() -> list[dict]:
    import yaml

    if not _DATA.exists():
        return []
    return (yaml.safe_load(_DATA.read_text(encoding="utf-8")) or {}).get("images") or []


def _norm(s: str) -> str:
    from app.services.seo_style import flatten

    return re.sub(r"\s+", " ", flatten(s or "")).strip()


def insertar(body_md: str, seccion: str, imagen_md: str) -> str | None:
    """El cuerpo con la imagen bajo el heading `seccion`; None si no está ese heading."""
    lineas = body_md.split("\n")
    for i, linea in enumerate(lineas):
        m = re.match(r"^#{2,3}\s+(.+?)\s*$", linea)
        if m and _norm(m.group(1)) == _norm(seccion):
            return "\n".join(lineas[: i + 1] + ["", imagen_md] + lineas[i + 1:])
    return None


@dataclass
class Resultado:
    target: str
    estado: str          # insertada | ya_estaba | sin_seccion | rechazada | error
    motivo: str = ""
    body_nuevo: str | None = None


def preparar(entrada: dict, body_md: str, *, rehost=None, verificar_fuente=None) -> Resultado:
    """Comprueba, re-aloja e inserta UNA foto. No escribe en la BD."""
    from app.services import image_guard

    target = entrada.get("target", "")
    url, seccion = entrada.get("url"), entrada.get("section")
    alt, credito = entrada.get("alt") or "", entrada.get("attribution") or ""
    fuente, licencia = entrada.get("source_url"), entrada.get("license") or ""
    identidad = entrada.get("identity") or alt
    if not (url and seccion and credito and fuente):
        return Resultado(target, "rechazada", "faltan url, section, attribution o source_url")
    if (entrada.get("rehosted_url") or url) in body_md:
        return Resultado(target, "ya_estaba")
    motivo = (verificar_fuente or image_guard.fuente_no_acredita)(fuente, identidad)
    if motivo:
        return Resultado(target, "rechazada", motivo)
    if rehost is None:
        from scripts.seo.fetch_entity_images import _rehost_to_cloudinary as rehost
    alojada = rehost(url) if image_guard.must_rehost(url) else url
    if not alojada:
        return Resultado(target, "error", "no se pudo re-alojar")
    v = image_guard.verify_provenance(entity_name=identidad, image_url=alojada,
                                      source_url=fuente, attribution=credito,
                                      license_=licencia)
    if not v.publishable:
        return Resultado(target, "rechazada", f"{v.status}: {v.reason}")
    if alojada in body_md:
        return Resultado(target, "ya_estaba")
    titulo = credito.replace('"', "'")
    nuevo = insertar(body_md, seccion, f'![{alt}]({alojada} "{titulo}")')
    if nuevo is None:
        return Resultado(target, "sin_seccion", f"no hay ningún heading «{seccion}»")
    return Resultado(target, "insertada", body_nuevo=nuevo)
