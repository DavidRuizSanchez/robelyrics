"""Descubre entidades RELEVANTES mencionadas en el contenido (seo_content +
posts) que todavía NO tienen página propia (slug_hint nulo y no presentes en
el corpus). Las agrupa por categoría y frecuencia para CURACIÓN HUMANA: el
operador decide cuáles merecen página y las añade al YAML correspondiente.

NO crea nada automáticamente (regla "nunca inventar en web pública").

Uso:  python -m scripts.seo.discover_entities [--min 1] [--top 40]
"""
from __future__ import annotations

import argparse
import logging
from collections import defaultdict

from app.db.models import (
    Album, Artist, Concept, Person, Place, Post, SeoContent, Song, Theme,
)
from app.db.session import SessionLocal
from app.services.entity_resolver import _normalize

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Tipo schema.org del LLM → sección destino del proyecto.
_TYPE_TO_SECTION = {
    "MusicGroup": "grupo", "MusicalGroup": "grupo", "Organization": "grupo",
    "Person": "persona",
    "Place": "lugar", "City": "lugar", "AdministrativeArea": "lugar",
    "TouristAttraction": "lugar", "Country": "lugar",
    "Thing": "concepto", "DefinedTerm": "concepto",
    "MusicAlbum": "obra", "MusicComposition": "obra", "MusicRecording": "obra",
    "CreativeWork": "obra", "Book": "obra",
}


def _corpus_names(db) -> set[str]:
    names: set[str] = set()
    for a in db.query(Artist).all():
        names.add(_normalize(a.name))
    for al in db.query(Album).all():
        names.add(_normalize(al.title))
    for s in db.query(Song).all():
        names.add(_normalize(s.title))
    for p in db.query(Person).all():
        names.add(_normalize(p.full_name))
        if p.stage_name:
            names.add(_normalize(p.stage_name))
    for pl in db.query(Place).all():
        names.add(_normalize(pl.name))
    for th in db.query(Theme).all():
        names.add(_normalize(th.name))
    for c in db.query(Concept).all():
        names.add(_normalize(c.name))
    return names


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min", type=int, default=1, help="Frecuencia mínima.")
    ap.add_argument("--top", type=int, default=40, help="Máx por categoría.")
    args = ap.parse_args()

    with SessionLocal() as db:
        corpus = _corpus_names(db)
        # {section: {norm_name: {"name", "count", "wikidata", "types"}}}
        cand: dict[str, dict[str, dict]] = defaultdict(dict)

        sources = []
        sources += [e for (e,) in db.query(SeoContent.entities).all() if e]
        sources += [e for (e,) in db.query(Post.entities).all() if e]

        for ents in sources:
            for ent in ents:
                if not isinstance(ent, dict):
                    continue
                if ent.get("slug_hint"):  # ya en corpus
                    continue
                name = (ent.get("name") or "").strip()
                norm = _normalize(name)
                if not norm or norm in corpus:
                    continue
                section = _TYPE_TO_SECTION.get(ent.get("type") or "", "otros")
                bucket = cand[section].setdefault(
                    norm, {"name": name, "count": 0, "wikidata": None, "types": set()}
                )
                bucket["count"] += 1
                bucket["types"].add(ent.get("type") or "?")
                if ent.get("wikidata_id") and not bucket["wikidata"]:
                    bucket["wikidata"] = ent["wikidata_id"]

        order = ["grupo", "lugar", "persona", "concepto", "obra", "otros"]
        for section in order:
            items = sorted(
                (v for v in cand.get(section, {}).values() if v["count"] >= args.min),
                key=lambda v: v["count"], reverse=True,
            )[: args.top]
            if not items:
                continue
            logger.info("══ %s · %d candidatos sin página ══", section.upper(), len(items))
            for v in items:
                wd = f" [{v['wikidata']}]" if v["wikidata"] else ""
                logger.info("  %2d×  %s%s  (%s)", v["count"], v["name"], wd,
                            "/".join(sorted(v["types"])))


if __name__ == "__main__":
    main()
