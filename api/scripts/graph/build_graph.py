"""Construye/repuebla el grafo de conocimiento unificado (`entity_edges`).

IDEMPOTENTE: deriva todas las aristas de las tablas relacionales + JSONB y
reescribe `entity_edges` por completo (delete-all + insert). Como el corpus es
de miles de filas, re-ejecutar es barato → sirve también para mantener el grafo
VIVO (se llama tras cada ingesta/seed y en el cron nocturno).

Aristas (src → dst), consultables en ambos sentidos por los índices:
  song_of_album, album_of_artist, song_theme, song_place, song_concept,
  member_of (person→artist), other_band (person→band), mentions (página→entidad).

Uso: python -m scripts.graph.build_graph [--verbose]
"""
from __future__ import annotations

import argparse
import re
import unicodedata

from sqlalchemy import delete

from app.db.models import (
    Album,
    Artist,
    Band,
    BandMembership,
    Concept,
    EntityEdge,
    Person,
    Place,
    Post,
    SeoContent,
    Song,
    SongConcept,
    SongPlace,
    SongTheme,
    Theme,
)
from app.db.session import SessionLocal
from scripts.seo.common import log


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


# URL pública → (entity_type) por prefijo de ruta (para resolver mentions).
_PATH_TYPE = {
    "personas": "person",
    "grupos": "band",
    "sellos": "band",
    "temas": "theme",
    "lugares": "place",
    "conceptos": "concept",
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    with SessionLocal() as db:
        # Mapas id→slug y slug→id por tipo (para resolver y etiquetar aristas).
        artists = {a.id: a for a in db.query(Artist).all()}
        albums = {a.id: a for a in db.query(Album).all()}
        songs = {s.id: s for s in db.query(Song).all()}
        persons = {p.id: p for p in db.query(Person).all()}
        bands = {b.id: b for b in db.query(Band).all()}
        themes = {t.id: t for t in db.query(Theme).all()}
        places = {p.id: p for p in db.query(Place).all()}
        concepts = {c.id: c for c in db.query(Concept).all()}

        slug_to_id: dict[str, dict[str, int]] = {
            "artist": {a.slug: a.id for a in artists.values()},
            "album": {a.slug: a.id for a in albums.values()},
            "song": {s.slug: s.id for s in songs.values()},
            "person": {p.slug: p.id for p in persons.values()},
            "band": {b.slug: b.id for b in bands.values()},
            "theme": {t.slug: t.id for t in themes.values()},
            "place": {p.slug: p.id for p in places.values()},
            "concept": {c.slug: c.id for c in concepts.values()},
        }
        slug_of = {
            "artist": {a.id: a.slug for a in artists.values()},
            "album": {a.id: a.slug for a in albums.values()},
            "song": {s.id: s.slug for s in songs.values()},
            "person": {p.id: p.slug for p in persons.values()},
            "band": {b.id: b.slug for b in bands.values()},
            "theme": {t.id: t.slug for t in themes.values()},
            "place": {p.id: p.slug for p in places.values()},
            "concept": {c.id: c.slug for c in concepts.values()},
        }

        # Dedup por clave única (src_type,src_id,edge_type,dst_type,dst_id), max weight.
        edges: dict[tuple, dict] = {}

        def add(st, sid, et, dt, did, *, weight=1.0, meta=None):
            if not sid or not did:
                return
            sslug = slug_of.get(st, {}).get(sid)
            dslug = slug_of.get(dt, {}).get(did)
            if not sslug or not dslug:
                return
            key = (st, sid, et, dt, did)
            prev = edges.get(key)
            if prev and prev["weight"] >= weight:
                return
            edges[key] = {
                "src_type": st, "src_id": sid, "src_slug": sslug,
                "edge_type": et, "dst_type": dt, "dst_id": did, "dst_slug": dslug,
                "weight": float(weight), "meta": meta,
            }

        # 1) Catálogo: song→album, album→artist
        for s in songs.values():
            add("song", s.id, "song_of_album", "album", s.album_id)
        for al in albums.values():
            add("album", al.id, "album_of_artist", "artist", al.artist_id)

        # 2) Taxonomías: song↔theme/place/concept
        for r in db.query(SongTheme).all():
            add("song", r.song_id, "song_theme", "theme", r.theme_id,
                weight=float(r.weight or 1.0))
        for r in db.query(SongPlace).all():
            add("song", r.song_id, "song_place", "place", r.place_id,
                meta=({"context": r.context} if r.context else None))
        for r in db.query(SongConcept).all():
            add("song", r.song_id, "song_concept", "concept", r.concept_id)

        # 3) Membresías: person→artist
        for m in db.query(BandMembership).all():
            add("person", m.person_id, "member_of", "artist", m.artist_id,
                weight=2.0, meta={"role": m.role, "era": m.era})

        # 4) other_bands (JSONB) → Band por nombre (best-effort)
        bands_by_norm = {_norm(b.name): b.id for b in bands.values()}
        for p in persons.values():
            for ob in (p.other_bands or []):
                name = ob.get("name") if isinstance(ob, dict) else None
                bid = bands_by_norm.get(_norm(name or ""))
                if bid:
                    add("person", p.id, "other_band", "band", bid, weight=1.5)

        # 5) mentions: páginas (seo_content/posts) → entidades del corpus
        def resolve_url(url: str) -> tuple[str, int] | None:
            if not url:
                return None
            path = url.split("?")[0].rstrip("/")
            parts = [x for x in path.split("/") if x]
            if not parts:
                return None
            if parts[0] in _PATH_TYPE:  # /personas/<slug>, /temas/<slug>, ...
                t = _PATH_TYPE[parts[0]]
                sid = slug_to_id[t].get(parts[-1])
                return (t, sid) if sid else None
            # /<artist>, /<artist>/<album>, /<artist>/<album>/<song>
            if len(parts) == 1 and parts[0] in slug_to_id["artist"]:
                return ("artist", slug_to_id["artist"][parts[0]])
            if len(parts) == 2 and parts[1] in slug_to_id["album"]:
                return ("album", slug_to_id["album"][parts[1]])
            if len(parts) >= 3 and parts[2] in slug_to_id["song"]:
                return ("song", slug_to_id["song"][parts[2]])
            return None

        mention_rows: list[tuple[str, int, list]] = []
        for sc in db.query(SeoContent).all():
            mention_rows.append((sc.entity_type, sc.entity_id, sc.entities or []))
        for po in db.query(Post).all():
            # los posts no son una entidad del grafo; sus mentions van como
            # aristas blog→entidad solo si quisiéramos; de momento se omiten para
            # no crear nodos "post". Se podrían añadir como dst de un nodo blog.
            pass
        for et, eid, ents in mention_rows:
            for m in ents:
                if not isinstance(m, dict):
                    continue
                if not m.get("from_corpus"):
                    continue
                resolved = resolve_url(m.get("url") or "")
                if not resolved:
                    continue
                dt, did = resolved
                if (et, eid) == (dt, did):
                    continue  # no auto-arista
                add(et, eid, "mentions", dt, did, weight=0.5)

        # Reescritura idempotente
        rows = list(edges.values())
        db.execute(delete(EntityEdge))
        if rows:
            db.bulk_insert_mappings(EntityEdge, rows)
        db.commit()

        # Resumen por tipo
        from collections import Counter
        by_type = Counter(r["edge_type"] for r in rows)
        log(f"grafo reconstruido: {len(rows)} aristas", "ok")
        for et, n in sorted(by_type.items()):
            log(f"  {et}: {n}")


if __name__ == "__main__":
    main()
