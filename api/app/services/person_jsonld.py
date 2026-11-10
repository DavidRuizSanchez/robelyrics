"""Relaciones curadas del JSON-LD de una persona (`data/person_jsonld.yaml`).

El JSON-LD de `/personas/<slug>` solo sabía decir `memberOf`, `knowsAbout` y
`hasOccupation`, y cada uno exigía un Q-ID de Wikidata. Dosis Letal, Indecisión
Momentánea o los murales de Jesús Mateos Brea no lo tienen, así que esas relaciones
no se podían expresar (10-11-2026). Este fichero las declara a mano, con su fuente,
y aquí se resuelven las referencias internas a `@id` reales.

Regla de siempre: una persona sin ficha publicada no existe para el público
(`person_visibility`), así que `person:<slug>` solo lleva `@id` y `url` si su ficha
se ve; si no, el nodo va con el nombre y nada más.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.services.entity_resolver import SITE_URL_DEFAULT

_DATA = Path(__file__).resolve().parents[2] / "data" / "person_jsonld.yaml"
_REF = re.compile(r"^(person|artist|place):([a-z0-9-]+)$")
_PRIVADAS = {"fuente"}


@lru_cache(maxsize=1)
def _cargar() -> dict[str, Any]:
    import yaml

    if not _DATA.exists():
        return {}
    return yaml.safe_load(_DATA.read_text(encoding="utf-8")) or {}


def _ref(db: Session, tipo: str, slug: str, base: str) -> dict | None:
    from app.db.models import Artist, Person, Place
    from app.services.person_visibility import ids_publicadas

    if tipo == "person":
        p = db.query(Person).filter(Person.slug == slug).first()
        if p is None:
            return None
        nodo = {"@type": "Person", "name": p.stage_name or p.full_name}
        if p.id in ids_publicadas(db):
            nodo |= {"@id": f"{base}/personas/{slug}#person", "url": f"{base}/personas/{slug}"}
        return nodo
    if tipo == "artist":
        a = db.query(Artist).filter(Artist.slug == slug).first()
        return a and {"@type": "MusicGroup", "@id": f"{base}/{slug}#musicgroup",
                      "name": a.name, "url": f"{base}/{slug}"}
    if tipo == "place":
        pl = db.query(Place).filter(Place.slug == slug).first()
        return pl and {"@type": "Place", "@id": f"{base}/lugares/{slug}#place",
                       "name": pl.name, "url": f"{base}/lugares/{slug}"}
    return None


def _resolver(db: Session, valor: Any, base: str) -> Any:
    if isinstance(valor, str):
        m = _REF.match(valor)
        if not m:
            return valor
        nodo = _ref(db, m.group(1), m.group(2), base)
        if nodo is None:
            # Una referencia rota es un error del yaml, no algo que inventar: fuera.
            raise ValueError(f"person_jsonld: referencia desconocida {valor!r}")
        return nodo
    if isinstance(valor, list):
        return [_resolver(db, v, base) for v in valor]
    if isinstance(valor, dict):
        return {k: _resolver(db, v, base) for k, v in valor.items() if k not in _PRIVADAS}
    return valor


def relaciones(db: Session, slug: str, *, site_url: str | None = None) -> dict | None:
    """Las propiedades curadas de la persona, listas para fusionar en su nodo."""
    datos = _cargar().get(slug)
    if not datos:
        return None
    return _resolver(db, datos, (site_url or SITE_URL_DEFAULT).rstrip("/"))
