"""Servicio del grafo de conocimiento (lee `entity_edges`).

- `neighbors`: aristas directas de una entidad (ambos sentidos).
- `subgraph`: BFS desde una entidad con tope de nodos → {nodes, edges} para
  visualizar/extraer "el universo de X" bajo demanda.
- `gather_connected`: para el dossier RAG → canciones conectadas (con el motivo
  de la conexión) + personas/bandas/álbumes relacionados.

Todas las conexiones aquí provienen de aristas REALES del grafo (datos curados),
por lo que se consideran verificadas por construcción (no necesitan web-check).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Album,
    Artist,
    Band,
    Concept,
    EntityEdge,
    Person,
    Place,
    Song,
    Theme,
)

# Cómo leer cada arista en lenguaje natural (para la provenance del dossier).
_EDGE_PHRASE = {
    "song_of_album": "es una canción del disco",
    "album_of_artist": "es un disco de",
    "song_theme": "trata el tema",
    "song_place": "menciona el lugar",
    "song_concept": "toca el concepto",
    "member_of": "fue parte de",
    "other_band": "también tocó en",
    "mentions": "se menciona en",
}

_MODELS = {
    "artist": Artist, "album": Album, "song": Song, "person": Person,
    "band": Band, "theme": Theme, "place": Place, "concept": Concept,
}


def _id_for(db: Session, entity_type: str, slug: str) -> int | None:
    m = _MODELS.get(entity_type)
    if not m:
        return None
    row = db.execute(select(m.id).where(m.slug == slug)).first()
    return row[0] if row else None


def _label(entity) -> str:
    for attr in ("stage_name", "full_name", "title", "name"):
        v = getattr(entity, attr, None)
        if v:
            return v
    return getattr(entity, "slug", "")


def resolve_labels(db: Session, nodes: set[tuple[str, int]]) -> dict[tuple[str, int], dict]:
    """{(type,id): {slug, label}} para un conjunto de nodos, en lote por tipo."""
    out: dict[tuple[str, int], dict] = {}
    by_type: dict[str, list[int]] = {}
    for t, i in nodes:
        by_type.setdefault(t, []).append(i)
    for t, ids in by_type.items():
        m = _MODELS.get(t)
        if not m:
            continue
        for e in db.execute(select(m).where(m.id.in_(ids))).scalars().all():
            out[(t, e.id)] = {"slug": e.slug, "label": _label(e)}
    return out


def _edges_touching(db: Session, t: str, i: int) -> list[EntityEdge]:
    return db.execute(
        select(EntityEdge).where(
            or_(
                and_(EntityEdge.src_type == t, EntityEdge.src_id == i),
                and_(EntityEdge.dst_type == t, EntityEdge.dst_id == i),
            )
        )
    ).scalars().all()


def neighbors(db: Session, entity_type: str, entity_id: int) -> list[dict]:
    """Vecinos directos: [{type, id, slug, edge_type, dir, weight, meta}]."""
    out = []
    for e in _edges_touching(db, entity_type, entity_id):
        if (e.src_type, e.src_id) == (entity_type, entity_id):
            out.append({"type": e.dst_type, "id": e.dst_id, "slug": e.dst_slug,
                        "edge_type": e.edge_type, "dir": "out", "weight": e.weight, "meta": e.meta})
        else:
            out.append({"type": e.src_type, "id": e.src_id, "slug": e.src_slug,
                        "edge_type": e.edge_type, "dir": "in", "weight": e.weight, "meta": e.meta})
    return out


def subgraph(db: Session, entity_type: str, slug: str, *, depth: int = 2,
             max_nodes: int = 60) -> dict:
    """BFS desde (entity_type, slug). Devuelve {center, nodes, edges}."""
    start_id = _id_for(db, entity_type, slug)
    if not start_id:
        return {"center": None, "nodes": [], "edges": []}
    start = (entity_type, start_id)
    nodes: set[tuple[str, int]] = {start}
    frontier = [start]
    edges: dict[tuple, dict] = {}
    for _ in range(max(1, depth)):
        nxt = []
        for (t, i) in frontier:
            for e in _edges_touching(db, t, i):
                key = (e.src_type, e.src_id, e.edge_type, e.dst_type, e.dst_id)
                edges[key] = {
                    "src": {"type": e.src_type, "id": e.src_id, "slug": e.src_slug},
                    "dst": {"type": e.dst_type, "id": e.dst_id, "slug": e.dst_slug},
                    "edge_type": e.edge_type, "weight": e.weight, "meta": e.meta,
                }
                other = (e.dst_type, e.dst_id) if (e.src_type, e.src_id) == (t, i) else (e.src_type, e.src_id)
                if other not in nodes and len(nodes) < max_nodes:
                    nodes.add(other)
                    nxt.append(other)
        frontier = nxt
        if not frontier:
            break
    labels = resolve_labels(db, nodes)
    # Solo conservar aristas cuyos dos extremos estén entre los nodos incluidos.
    edge_list = [
        e for e in edges.values()
        if (e["src"]["type"], e["src"]["id"]) in nodes and (e["dst"]["type"], e["dst"]["id"]) in nodes
    ]
    node_list = [
        {"type": t, "id": i, **labels.get((t, i), {"slug": "", "label": ""})}
        for (t, i) in nodes
    ]
    return {
        "center": {"type": entity_type, "id": start_id, **labels.get(start, {})},
        "nodes": node_list,
        "edges": edge_list,
    }


# --------------------------------------------------------------------------- #
# gather_connected: material conectado para el dossier RAG
# --------------------------------------------------------------------------- #
@dataclass
class ConnectedSong:
    song_id: int
    slug: str
    title: str
    album: str
    year: int | None
    why: str          # provenance legible ("trata el tema «Muerte»", "del disco Agila"…)
    weight: float


@dataclass
class Connected:
    songs: list[ConnectedSong] = field(default_factory=list)
    people: list[dict] = field(default_factory=list)   # {slug,label,why}
    bands: list[dict] = field(default_factory=list)
    albums: list[dict] = field(default_factory=list)

    @property
    def song_ids(self) -> list[int]:
        return [s.song_id for s in self.songs]


def gather_connected(db: Session, entity_type: str, entity, *, max_songs: int = 15) -> Connected:
    """Reúne lo conectado a la entidad para alimentar el dossier, con el MOTIVO
    de cada conexión (provenance). Recorre hasta 2 saltos para llegar a canciones.
    """
    out = Connected()
    subject = _label(entity)
    eid = entity.id

    def add_song(s: Song, why: str, weight: float):
        if any(cs.song_id == s.id for cs in out.songs):
            return
        al = getattr(s, "album", None)
        out.songs.append(ConnectedSong(
            song_id=s.id, slug=s.slug, title=s.title,
            album=(al.title if al else ""), year=(al.year if al else None),
            why=why, weight=weight,
        ))

    def songs_of_artist(artist_id: int, why: str, *, year_range: tuple[int, int] | None = None):
        rows = db.execute(
            select(Song).join(Album, Song.album_id == Album.id)
            .where(Album.artist_id == artist_id)
        ).scalars().all()
        for s in rows:
            if year_range:
                yr = getattr(getattr(s, "album", None), "year", None)
                if yr and not (year_range[0] <= yr <= year_range[1]):
                    continue  # fuera de la etapa de la persona
            add_song(s, why, 1.0)

    if entity_type in ("theme", "place", "concept"):
        # Canciones que tratan este tema/lugar/concepto (relationship directo).
        for s in (getattr(entity, "songs", None) or []):
            phrase = {"theme": "trata el tema", "place": "menciona el lugar",
                      "concept": "toca el concepto"}[entity_type]
            add_song(s, f"{phrase} «{subject}»", 2.0)

    elif entity_type == "album":
        for s in (getattr(entity, "songs", None) or []):
            add_song(s, f"pertenece al disco «{subject}»", 2.0)

    elif entity_type == "artist":
        songs_of_artist(eid, f"es de {subject}")

    elif entity_type == "song":
        add_song(entity, "es la propia canción", 3.0)
        # Vecinas por taxonomía compartida (vía neighbors → temas/conceptos → otras canciones).
        for n in neighbors(db, "song", eid):
            if n["edge_type"] in ("song_theme", "song_concept", "song_place") and n["dir"] == "out":
                tax_type, tax_id = n["type"], n["id"]
                for e in _edges_touching(db, tax_type, tax_id):
                    other_song_id = None
                    if e.src_type == "song" and e.src_id != eid:
                        other_song_id = e.src_id
                    elif e.dst_type == "song" and e.dst_id != eid:
                        other_song_id = e.dst_id
                    if other_song_id:
                        s = db.get(Song, other_song_id)
                        if s:
                            add_song(s, f"comparte {_EDGE_PHRASE.get(n['edge_type'],'rasgo')} «{n['slug']}» con «{subject}»", 1.0)

    elif entity_type == "person":
        for n in neighbors(db, "person", eid):
            if n["edge_type"] == "member_of":
                era = (n.get("meta") or {}).get("era")
                role = (n.get("meta") or {}).get("role")
                why_artist = f"{subject} fue {role or 'parte'} de esta banda" + (f" ({era})" if era else "")
                out.bands.append({"slug": n["slug"], "label": n["slug"], "why": why_artist})
                m = re.match(r"(\d{4})\D+(\d{4})", era or "")
                yr_range = (int(m.group(1)), int(m.group(2))) if m else None
                why_song = f"de {n['slug']}, banda de {subject}" + (f" en su etapa {era}" if era else "")
                songs_of_artist(n["id"], why_song, year_range=yr_range)
            elif n["edge_type"] == "other_band":
                out.bands.append({"slug": n["slug"], "label": n["slug"], "why": f"{subject} también tocó aquí"})

    elif entity_type == "band":
        # Personas que pertenecieron / la citan en other_bands.
        for n in neighbors(db, "band", eid):
            if n["edge_type"] == "other_band" and n["type"] == "person":
                out.people.append({"slug": n["slug"], "label": n["slug"], "why": "tocó en esta banda"})

    # Recortar canciones por peso (desc) y tope.
    out.songs.sort(key=lambda s: s.weight, reverse=True)
    out.songs = out.songs[:max_songs]
    return out
