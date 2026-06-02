"""Selección de imagen heroica para posts del blog, RELEVANTE por construcción.

Regla (estricta): la foto de un post debe estar directamente relacionada con
lo que se cuenta. En vez de una búsqueda libre en Wikimedia por el título
(que devuelve cualquier cosa), se usa la **imagen curada de la entidad
protagonista** del post: la primera entidad reconocida del corpus con imagen
(Robe/Extremoduro, una persona, un disco, un grupo, un lugar…).

Así la imagen es siempre del sujeto real del que habla el post y, además,
tiene licencia limpia (ya verificada al curar esa entidad).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

# Prioridad de tipo cuando varias entidades tienen imagen: lo más específico/
# icónico primero. (Orden de aparición se respeta dentro de cada barrido.)
_TYPE_ORDER = ["MusicAlbum", "MusicComposition", "Person", "MusicGroup", "Place"]


def _entity_image(db: Session, etype: str, slug: str) -> dict[str, Any] | None:
    from app.db.models import (
        Album, Artist, Band, Concept, Person, Place, Song, Theme,
    )
    etype = (etype or "").strip()

    if etype == "Person":
        p = db.query(Person).filter(Person.slug == slug).first()
        if p and p.image_url:
            return {"url": p.image_url, "attribution": p.image_attribution,
                    "license": p.image_license, "source": p.image_source_url}
        return None

    if etype == "MusicGroup":
        a = db.query(Artist).filter(Artist.slug == slug).first()
        if a and getattr(a, "image_url", None):
            return {"url": a.image_url, "attribution": getattr(a, "image_attribution", None),
                    "license": getattr(a, "image_license", None),
                    "source": getattr(a, "image_source_url", None)}
        b = db.query(Band).filter(Band.slug == slug).first()
        if b and b.image_url:
            return {"url": b.image_url, "attribution": b.image_attribution,
                    "license": b.image_license, "source": b.image_source_url}
        return None

    if etype == "MusicAlbum":
        al = db.query(Album).filter(Album.slug == slug).first()
        if al and al.cover_url:
            return {"url": al.cover_url, "attribution": f"Portada de «{al.title}»",
                    "license": None, "source": None}
        return None

    if etype == "MusicComposition":
        s = db.query(Song).filter(Song.slug == slug).first()
        if s:
            cover = s.cover_url or (s.album.cover_url if s.album else None)
            if cover:
                return {"url": cover, "attribution": f"«{s.title}»",
                        "license": None, "source": None}
        return None

    if etype == "Place":
        pl = db.query(Place).filter(Place.slug == slug).first()
        if pl and pl.image_url:
            return {"url": pl.image_url, "attribution": pl.image_attribution,
                    "license": pl.image_license, "source": pl.image_source_url}
        return None

    return None


def pick_hero_image(db: Session, entities: list[dict] | None) -> dict[str, Any] | None:
    """Imagen de la entidad protagonista del post. Devuelve
    {url, attribution, license, source} o None.

    Respeta el orden de aparición de las entidades (la primera nombrada suele
    ser el sujeto), con un pequeño sesgo de tipo para preferir lo icónico.
    """
    ents = [e for e in (entities or []) if e.get("slug_hint")]
    if not ents:
        return None
    # Primer barrido por prioridad de tipo (álbum/canción/persona…); si nada,
    # segundo barrido por orden de aparición con cualquier tipo soportado.
    for etype in _TYPE_ORDER:
        for e in ents:
            if e.get("type") == etype:
                img = _entity_image(db, etype, e["slug_hint"])
                if img:
                    return img
    for e in ents:
        img = _entity_image(db, e.get("type", ""), e["slug_hint"])
        if img:
            return img
    return None
