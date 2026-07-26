"""Mide el HEADROOM de material de cada ficha: cuánta sustancia real del corpus hay
disponible frente a lo que el cuerpo ACTUAL ya usa. Sirve para pre-filtrar (barato,
solo BD, sin LLM) qué páginas cortas merece regenerar a cornerstone (tienen material
que no están aprovechando) y cuáles son flacas de verdad (dejar cortas y honestas).

Señal de richness (0..1) reusando la lógica de engagement.py, por tipo:
  - song:   grado de grafo + nº de interpretaciones fan + longitud de la letra.
  - album:  nº de canciones + riqueza agregada del tracklist.
  - band/person: grado de grafo + fan-sources + longitud de bio_long.
  - theme/concept: nº de canciones que tocan el tema.
  - place:  grado de grafo + nº de canciones que lo mencionan.

Headroom = richness ALTA con cuerpo CORTO (mucho material sin verter). Se marca
`expandible` si richness >= umbral y el cuerpo está por debajo de su objetivo de tipo.

Uso:
  python -m scripts.seo.measure_headroom
  python -m scripts.seo.measure_headroom --max-chars 3500
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy import func, or_, select

from app.db.models import (
    Album,
    Artist,
    Band,
    Concept,
    EntityEdge,
    InterpretationSource,
    Person,
    Place,
    SeoContent,
    Song,
    SongInterpretation,
    Theme,
)
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_MODEL = {"song": Song, "album": Album, "band": Band, "person": Person,
          "place": Place, "theme": Theme, "concept": Concept, "artist": Artist}

# Objetivo de longitud "flagship" por tipo (aprox): por debajo = candidato a crecer.
_TARGET = {"song": 4500, "album": 5500, "band": 4500, "person": 4500,
           "place": 3800, "theme": 5000, "concept": 5000, "artist": 8000}


def _degree(db, slug: str) -> int:
    return int(db.execute(
        select(func.count()).select_from(EntityEdge).where(EntityEdge.src_slug == slug)
    ).scalar() or 0)


def _song_richness(db, song: Song) -> float:
    deg = _degree(db, song.slug)
    n_interp = int(db.execute(
        select(func.count()).select_from(SongInterpretation)
        .where(SongInterpretation.song_id == song.id)).scalar() or 0)
    n_src = int(db.execute(
        select(func.count()).select_from(InterpretationSource)
        .where(InterpretationSource.referenced_song_ids.any(song.id))).scalar() or 0)
    lyr = len(getattr(song, "lyrics_clean", "") or "")
    return min(1.0, 0.30 * min(deg / 12, 1) + 0.35 * min(n_interp / 8, 1)
              + 0.20 * min(n_src / 10, 1) + 0.15 * min(lyr / 1500, 1))


def _generic_richness(db, ent, slug: str, bio_attr: str | None = None) -> float:
    deg = _degree(db, slug)
    bio = len(getattr(ent, bio_attr, "") or "") if bio_attr else 0
    return min(1.0, 0.6 * min(deg / 14, 1) + 0.4 * min(bio / 2500, 1))


def _tax_richness(db, ent) -> float:
    n = len(ent.songs) if getattr(ent, "songs", None) else 0
    return min(1.0, n / 12)


def _richness(db, etype: str, ent) -> float:
    if etype == "song":
        return _song_richness(db, ent)
    if etype in ("theme", "concept"):
        return _tax_richness(db, ent)
    if etype in ("person", "band", "artist"):
        return _generic_richness(db, ent, ent.slug, "bio_long")
    if etype == "album":
        n = len(ent.songs) if getattr(ent, "songs", None) else 0
        return min(1.0, 0.5 * min(n / 12, 1) + 0.5 * min(_degree(db, ent.slug) / 20, 1))
    if etype == "place":
        return _generic_richness(db, ent, ent.slug)
    return _generic_richness(db, ent, ent.slug)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-chars", type=int, default=3500,
                    help="solo evalúa páginas por debajo de esto")
    ap.add_argument("--rich", type=float, default=0.45,
                    help="richness mínima para marcar como expandible")
    args = ap.parse_args()

    rows = []
    with SessionLocal() as db:
        for sc in db.query(SeoContent).all():
            ln = len(sc.body_md or "")
            if ln >= args.max_chars:
                continue
            model = _MODEL.get(sc.entity_type)
            ent = db.get(model, sc.entity_id) if model else None
            if not ent:
                continue
            r = _richness(db, sc.entity_type, ent)
            target = _TARGET.get(sc.entity_type, 4500)
            expandible = r >= args.rich and ln < target * 0.85
            rows.append((sc.entity_type, sc.slug, ln, round(r, 2), target, expandible))

    rows.sort(key=lambda x: (-x[5], -x[3]))
    exp = [r for r in rows if r[5]]
    by_type = {}
    for r in exp:
        by_type[r[0]] = by_type.get(r[0], 0) + 1
    print(f"\nPáginas cortas (<{args.max_chars}c): {len(rows)}")
    print(f"EXPANDIBLES (richness>={args.rich} y cuerpo corto): {len(exp)}")
    print("  por tipo:", dict(sorted(by_type.items())))
    print(f"\nTop 30 expandibles (richness · chars actuales · tipo · slug):")
    for etype, slug, ln, r, tgt, e in exp[:30]:
        print(f"  {r:.2f}  {ln:>5}c  {etype:<8} {slug}")
    print(f"\nFLACAS (corto pero poco material, se dejan honestas): {len(rows) - len(exp)}")
    # muestra de flacas para verificar el criterio
    thin = [r for r in rows if not r[5]][:10]
    for etype, slug, ln, r, tgt, e in thin:
        print(f"  {r:.2f}  {ln:>5}c  {etype:<8} {slug}")


if __name__ == "__main__":
    main()
