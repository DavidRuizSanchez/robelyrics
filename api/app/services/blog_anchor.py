"""Resolución de la ENTIDAD CENTRAL de una propuesta de blog `evergreen` que se
creó como keyword-driven (`source_type='seo'`).

Motivación: los evergreen 'seo' se generaban con `generate_seo_article`, un
one-shot de 500-900 palabras que produce piezas finas ("paja"). Si el artículo
gira en torno a una entidad REAL del corpus (una persona, una banda/proyecto, el
propio Robe, un disco, una canción o una temática), podemos anclarlo a ella y
generarlo con el MISMO motor profundo (dossier RAG + outline + sección a sección
+ verificación) que las páginas de entidad y las noticias ricas.

Este módulo NO genera nada: solo decide, de forma conservadora y trazable, a qué
entidad ancla una propuesta. Si no hay match específico y fiable, devuelve None y
el generador cae al one-shot clásico (que el gate de rigor retendrá si es flojo).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.db.models import Album, Artist, Band, Concept, Person, Place, Song, Theme

# Tipos que el motor profundo (deep_research.gather_entity_dossier) entiende.
DEEP_TYPES = ("person", "band", "artist", "album", "song", "theme", "concept", "place")

# Peso por tipo: para un evergreen, una persona/banda/artista concretos son un
# ancla central más fuerte que una temática genérica; una canción suele ser
# materia de 'spotlight', no de evergreen, así que pesa menos aquí.
_TYPE_WEIGHT = {
    "person": 5, "band": 5, "artist": 5,
    "album": 4, "theme": 3, "concept": 3,
    "song": 2, "place": 1,
}

# Longitud mínima del nombre normalizado para considerarlo (evita que un token
# corto y ambiguo dispare un anclaje). Los nombres nucleares monopalabra
# ("robe", "leño") se permiten explícitamente por su alta especificidad.
_MIN_LEN = 4
_CORE_SINGLE = {"robe", "leno", "extremoduro"}


@dataclass
class Anchor:
    entity_type: str
    entity: object
    name: str
    score: float
    matched_in: str  # "keyword" | "title" | "angle"


def _norm(s: str | None) -> str:
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"\s+", " ", ascii_only).strip()


def _clean_title(title: str) -> str:
    """Quita sufijos entre paréntesis de un título de canción/disco:
    «Jesucristo García (Rock Transgresivo)» → «Jesucristo García»."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", title or "").strip()


def _whole_match(needle: str, haystack: str) -> bool:
    """`needle` aparece como palabra(s) completa(s) dentro de `haystack`."""
    if not needle or not haystack:
        return False
    return re.search(rf"(?<![\w]){re.escape(needle)}(?![\w])", haystack) is not None


def _candidates(db) -> list[tuple[str, object, str]]:
    """[(entity_type, entity, norm_name)] de las entidades enlazables del corpus."""
    out: list[tuple[str, object, str]] = []

    def add(etype: str, ent: object, *names: str | None) -> None:
        for nm in names:
            n = _norm(nm)
            if not n:
                continue
            if " " not in n and len(n) < _MIN_LEN and n not in _CORE_SINGLE:
                continue
            out.append((etype, ent, n))

    for a in db.query(Artist).all():
        add("artist", a, a.name)
    for b in db.query(Band).all():
        add("band", b, b.name)
    for p in db.query(Person).all():
        add("person", p, p.full_name, p.stage_name)
    for al in db.query(Album).all():
        add("album", al, al.title, _clean_title(al.title))
    for s in db.query(Song).all():
        add("song", s, s.title, _clean_title(s.title))
    for th in db.query(Theme).all():
        add("theme", th, th.name)
    for c in db.query(Concept).all():
        add("concept", c, c.name)
    for pl in db.query(Place).all():
        add("place", pl, pl.name)
    return out


def resolve_central_entity(
    db, *, primary_keyword: str | None, title: str | None, angle: str | None,
) -> Anchor | None:
    """Devuelve el ancla más específica y fiable, o None si no hay match claro.

    Prioriza dónde aparece el nombre (keyword de búsqueda > titular > ángulo),
    su especificidad (nombres largos/multipalabra) y el peso del tipo. Conservador:
    ante la duda (ningún candidato lo bastante específico), devuelve None."""
    fields = [
        ("keyword", _norm(primary_keyword), 3.0),
        ("title", _norm(title), 2.0),
        ("angle", _norm(angle), 1.0),
    ]
    best: Anchor | None = None
    for etype, ent, cand in _candidates(db):
        tw = _TYPE_WEIGHT.get(etype, 1)
        # Especificidad: nº de palabras del nombre + un pequeño extra por longitud.
        words = cand.count(" ") + 1
        specificity = words * 2.0 + min(len(cand), 30) / 15.0
        for where, text, wsrc in fields:
            if not text or not _whole_match(cand, text):
                continue
            score = wsrc * (specificity + tw * 0.6)
            if best is None or score > best.score:
                name = getattr(ent, "name", None) or getattr(ent, "stage_name", None) \
                    or getattr(ent, "full_name", None) or getattr(ent, "title", None) or cand
                best = Anchor(entity_type=etype, entity=ent, name=name,
                              score=round(score, 2), matched_in=where)
            break  # ya casó en el campo de mayor prioridad para este candidato
    return best
