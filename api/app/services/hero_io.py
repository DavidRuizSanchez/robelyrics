"""Lectura y escritura ATÓMICA del paquete de imagen hero de un Post/ContentProposal.

El hero son 5 campos que SIEMPRE deben viajar juntos: la URL de la imagen y sus
metadatos (alt, atribución, licencia, fuente). Si un script escribe solo la URL y
deja el crédito viejo, la imagen y su pie de foto se DESINCRONIZAN (una foto de X
con el crédito de Y). Ese fue el bug del post de Rosendo.

Regla del proyecto: nadie toca `hero_image_*` campo a campo. Todo el mundo usa
`apply_hero` (escribir el paquete completo o limpiarlo entero) y `read_hero`
(leerlo como una unidad). Así url y crédito no pueden divergir por construcción.

El dict de hero tiene la forma canónica que ya produce `blog_hero.build_unique_hero`
y `hero_image.pick_hero_image`:

    {"url": str, "alt": str|None, "attribution": str|None,
     "license": str|None, "source": str|None}
"""
from __future__ import annotations

from typing import Any

# Claves del dict de hero  ->  atributo del modelo. Un solo sitio que mapea ambos.
_HERO_MAP: tuple[tuple[str, str], ...] = (
    ("url", "hero_image_url"),
    ("alt", "hero_image_alt"),
    ("attribution", "hero_image_attribution"),
    ("license", "hero_image_license"),
    ("source", "hero_image_source_url"),
)


def apply_hero(target: Any, hero: dict | None) -> None:
    """Escribe los 5 campos hero de `target` de forma atómica.

    - `hero` dict → escribe url/alt/attribution/license/source (las ausentes = None).
    - `hero` None → limpia los 5 campos (deja el post sin imagen, coherentemente).

    Nunca deja un subconjunto: o el paquete entero nuevo, o vacío. Es la única vía
    permitida para tocar el hero.
    """
    for key, attr in _HERO_MAP:
        setattr(target, attr, (hero or {}).get(key))


def read_hero(source: Any) -> dict | None:
    """Lee los 5 campos hero de `source` como paquete, o None si no hay URL.

    Devuelve un dict con la forma canónica ({url, alt, attribution, license,
    source}) apto para pasarlo tal cual a `apply_hero` en otro objeto. Si no hay
    `hero_image_url`, devuelve None (no hay imagen que arrastrar)."""
    if source is None or not getattr(source, "hero_image_url", None):
        return None
    return {key: getattr(source, attr) for key, attr in _HERO_MAP}
