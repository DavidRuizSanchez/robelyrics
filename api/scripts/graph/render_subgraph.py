"""Renderiza subgrafos del knowledge graph bajo demanda.

- `--entity <type>/<slug>`: el "universo" de una entidad (BFS) → Mermaid o DOT.
- `--meta`: el meta-grafo (tipos de entidad + tipos de arista con conteos).

Mermaid es texto y se renderiza en GitHub/markdown/mermaid.live; DOT se puede
pasar por Graphviz (`dot -Tsvg`) si está instalado.

Uso:
  python -m scripts.graph.render_subgraph --entity person/inaki-milindris --depth 2
  python -m scripts.graph.render_subgraph --meta
  python -m scripts.graph.render_subgraph --entity place/barakaldo --format dot --out /tmp/barakaldo.dot
"""
from __future__ import annotations

import argparse
import re

from sqlalchemy import func, select

from app.db.models import EntityEdge
from app.db.session import SessionLocal
from app.services import graph as g

_TYPE_EMOJI = {
    "artist": "🎤", "album": "💿", "song": "🎵", "person": "🧑",
    "band": "🎸", "theme": "🏷️", "place": "📍", "concept": "💭",
}


def _nid(t: str, i: int) -> str:
    return f"{t}_{i}"


def _esc(s: str) -> str:
    return (s or "").replace('"', "'").replace("\n", " ").strip()


def _mermaid_subgraph(sg: dict) -> str:
    lines = ["graph LR"]
    center = sg.get("center") or {}
    for n in sg["nodes"]:
        emoji = _TYPE_EMOJI.get(n["type"], "")
        nid = _nid(n["type"], n["id"])
        label = f'{emoji} {_esc(n.get("label") or n.get("slug"))}'
        lines.append(f'  {nid}["{label}"]')
        if center and n["type"] == center.get("type") and n["id"] == center.get("id"):
            lines.append(f"  style {nid} fill:#a83a3a,color:#fff,stroke:#fff")
    for e in sg["edges"]:
        s = _nid(e["src"]["type"], e["src"]["id"])
        d = _nid(e["dst"]["type"], e["dst"]["id"])
        lines.append(f'  {s} -->|{e["edge_type"]}| {d}')
    return "\n".join(lines)


def _dot_subgraph(sg: dict) -> str:
    lines = ["digraph G {", '  rankdir=LR; node [shape=box, style=rounded];']
    for n in sg["nodes"]:
        nid = _nid(n["type"], n["id"])
        lines.append(f'  "{nid}" [label="{_esc(n.get("label") or n.get("slug"))}\\n({n["type"]})"];')
    for e in sg["edges"]:
        s = _nid(e["src"]["type"], e["src"]["id"])
        d = _nid(e["dst"]["type"], e["dst"]["id"])
        lines.append(f'  "{s}" -> "{d}" [label="{e["edge_type"]}"];')
    lines.append("}")
    return "\n".join(lines)


def _meta_graph(db, fmt: str) -> str:
    rows = db.execute(
        select(EntityEdge.src_type, EntityEdge.edge_type, EntityEdge.dst_type, func.count())
        .group_by(EntityEdge.src_type, EntityEdge.edge_type, EntityEdge.dst_type)
        .order_by(func.count().desc())
    ).all()
    if fmt == "dot":
        out = ["digraph Meta {", "  rankdir=LR; node [shape=box, style=rounded];"]
        for st, et, dt, n in rows:
            out.append(f'  "{st}" -> "{dt}" [label="{et} ({n})"];')
        out.append("}")
        return "\n".join(out)
    out = ["graph LR"]
    seen = set()
    for st, et, dt, n in rows:
        for t in (st, dt):
            if t not in seen:
                seen.add(t)
                out.append(f'  {t}["{_TYPE_EMOJI.get(t,"")} {t}"]')
        out.append(f'  {st} -->|{et} · {n}| {dt}')
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entity", help="<type>/<slug>, p.ej. person/inaki-milindris")
    ap.add_argument("--meta", action="store_true", help="meta-grafo de tipos+aristas")
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--max-nodes", type=int, default=50)
    ap.add_argument("--format", choices=["mermaid", "dot"], default="mermaid")
    ap.add_argument("--out", help="fichero de salida (si no, stdout)")
    args = ap.parse_args()

    with SessionLocal() as db:
        if args.meta:
            text = _meta_graph(db, args.format)
        elif args.entity:
            etype, _, slug = args.entity.partition("/")
            sg = g.subgraph(db, etype, slug, depth=args.depth, max_nodes=args.max_nodes)
            if not sg.get("center"):
                raise SystemExit(f"entidad no encontrada: {args.entity}")
            text = _mermaid_subgraph(sg) if args.format == "mermaid" else _dot_subgraph(sg)
        else:
            raise SystemExit("usa --entity <type>/<slug> o --meta")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"escrito en {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
