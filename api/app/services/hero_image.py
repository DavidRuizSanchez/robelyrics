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

import re
import unicodedata
from typing import Any

from sqlalchemy.orm import Session

# Prioridad de tipo cuando varias entidades tienen imagen: lo más específico/
# icónico primero. (Orden de aparición se respeta dentro de cada barrido.)
_TYPE_ORDER = ["MusicAlbum", "MusicComposition", "Person", "MusicGroup", "Place"]

# Palabras vacías que no distinguen un protagonista.
_STOP = {
    "de", "la", "el", "los", "las", "y", "en", "del", "un", "una", "su", "a",
    "que", "con", "por", "para", "al", "lo", "sus", "e",
}


def _norm_tokens(text: str) -> set[str]:
    """Tokens significativos, en minúsculas y sin acentos."""
    if not text:
        return set()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    toks = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in toks if t not in _STOP and len(t) > 1}


def _subject_match(entity: dict, subj_tokens: set[str]) -> float:
    """Fracción del nombre de la entidad presente en el sujeto (0..1).

    1.0 = el nombre entero de la entidad aparece en el sujeto (probable
    protagonista); 0.0 = no aparece (entidad meramente relacionada)."""
    label = entity.get("label") or entity.get("name") or entity.get("slug_hint") or ""
    et = _norm_tokens(label)
    if not et or not subj_tokens:
        return 0.0
    return len(et & subj_tokens) / len(et)


def _entity_image(db: Session, etype: str, slug: str) -> dict[str, Any] | None:
    from app.db.models import (
        Album, Artist, Band, Concept, Person, Place, Song, Theme,
    )
    etype = (etype or "").strip()

    if etype == "Person":
        p = db.query(Person).filter(Person.slug == slug).first()
        if p and p.image_url:
            display = p.stage_name or p.full_name
            return {"url": p.image_url, "attribution": p.image_attribution,
                    "license": p.image_license, "source": p.image_source_url,
                    "alt": f"Fotografía de {display}"}
        return None

    if etype == "MusicGroup":
        a = db.query(Artist).filter(Artist.slug == slug).first()
        if a and getattr(a, "image_url", None):
            return {"url": a.image_url, "attribution": getattr(a, "image_attribution", None),
                    "license": getattr(a, "image_license", None),
                    "source": getattr(a, "image_source_url", None),
                    "alt": f"El grupo {a.name}"}
        b = db.query(Band).filter(Band.slug == slug).first()
        if b and b.image_url:
            return {"url": b.image_url, "attribution": b.image_attribution,
                    "license": b.image_license, "source": b.image_source_url,
                    "alt": f"El grupo {b.name}"}
        return None

    if etype == "MusicAlbum":
        al = db.query(Album).filter(Album.slug == slug).first()
        if al and al.cover_url:
            return {"url": al.cover_url, "attribution": f"Portada de «{al.title}»",
                    "license": None, "source": None,
                    "alt": f"Portada del disco «{al.title}»"}
        return None

    if etype == "MusicComposition":
        # El slug de canción solo es único dentro del disco: con `.first()`, una
        # homónima devolvía la portada del disco equivocado. Con varias, manda la
        # de estudio; si sigue habiendo empate, mejor sin portada que con otra.
        from app.services.url_resolver import is_live_version

        _cands = db.query(Song).filter(Song.slug == slug).order_by(Song.id).all()
        s = _cands[0] if len(_cands) == 1 else None
        if s is None and _cands:
            _estudio = [c for c in _cands if not is_live_version(c.slug, c.title)]
            s = _estudio[0] if len(_estudio) == 1 else None
        if s:
            cover = s.cover_url or (s.album.cover_url if s.album else None)
            if cover:
                alt = (f"Portada de «{s.album.title}», disco de la canción «{s.title}»"
                       if s.album else f"Carátula de «{s.title}»")
                return {"url": cover, "attribution": f"«{s.title}»",
                        "license": None, "source": None, "alt": alt}
        return None

    if etype == "Place":
        pl = db.query(Place).filter(Place.slug == slug).first()
        if pl and pl.image_url:
            return {"url": pl.image_url, "attribution": pl.image_attribution,
                    "license": pl.image_license, "source": pl.image_source_url,
                    "alt": pl.name}
        return None

    return None


def pick_hero_image(
    db: Session,
    entities: list[dict] | None,
    *,
    used: set[str] | None = None,
    subject: str = "",
) -> dict[str, Any] | None:
    """Imagen de la entidad PROTAGONISTA del post. Devuelve
    {url, attribution, license, source, alt} o None.

    `subject` (target_keyword/título): se usa para PREFERIR la entidad que es el
    sujeto real del post. Si el post va de alguien que coincide con el sujeto, se
    coge SU imagen; las entidades meramente relacionadas (p.ej. Robe citado en un
    post sobre Rosendo) quedan detrás. Así se evita heredar la cara de una entidad
    relacionada. La garantía final de relevancia la pone el gate de `hero_guard`.

    `used`: URLs ya empleadas por otros posts. Se SALTAN para no repetir imagen
    entre posts (regla dura). Si nada sirve, devuelve None → el caller cae a foto
    web del protagonista y, si no, al arte IA propio.
    """
    used = used or set()
    ents = [e for e in (entities or []) if e.get("slug_hint")]
    if not ents:
        return None

    # Orden por afinidad con el sujeto (protagonista primero), estable: a igual
    # afinidad se respeta el orden de aparición original.
    subj_tokens = _norm_tokens(subject)
    scored = sorted(ents, key=lambda e: -_subject_match(e, subj_tokens))
    # ¿Hay alguna entidad que sea claramente el protagonista (nombre presente en
    # el sujeto)? Si la hay, restringimos a las protagonistas y NO tomamos prestada
    # la imagen de una entidad relacionada. Si ninguna coincide (post temático:
    # una taxonomía, un mood…), usamos todas como antes.
    protagonists = [e for e in scored if _subject_match(e, subj_tokens) >= 0.5]
    pool = protagonists or scored

    # Primer barrido por prioridad de tipo; luego por orden ya rankeado.
    for etype in _TYPE_ORDER:
        for e in pool:
            if e.get("type") == etype:
                img = _entity_image(db, etype, e["slug_hint"])
                if img and img["url"] not in used:
                    return img
    for e in pool:
        img = _entity_image(db, e.get("type", ""), e["slug_hint"])
        if img and img["url"] not in used:
            return img
    return None
