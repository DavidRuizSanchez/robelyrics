"""Auditoría de cobertura del corpus: ¿lo que tenemos ingerido SIRVE a alguien?

Vectorizar no es servir. En julio de 2026 las 731 fuentes del corpus estaban al
100% en `interpretations_v1` y, aun así, 420 de ellas eran IRRECUPERABLES: la
única función que leía esa colección devolvía `payload.song_ids` para boostear el
ranking, y esas fuentes no estaban ligadas a ninguna canción, así que su texto no
podía salir en ninguna respuesta. Entre ellas 141 transcripciones de YouTube
(≈2,6 M de caracteres) y las 110 anotaciones de Genius, que además estaban
excluidas del otro camino (el ILIKE por nombre de entidad).

Este script mide eso, para que el número sea una métrica vigilada y no el hallazgo
de una tarde. Por cada `kind` comprueba los TRES caminos de recuperación que hay:

  song_ids   → `search_interpretations_for_song_ids` (boost del buscador y afinidad).
  entidad    → `fetch_sources_for_entity`, ILIKE por nombre (excluye genius_annotation).
  semántico  → `search_interpretations_passages`, devuelve el pasaje sin depender
               del enlace a canción. Es el que rescata a los huérfanos.

Una fuente cuenta como SERVIDA si al menos un camino puede devolverla. Las que no,
salen listadas: son las que hay que enlazar, destilar o revisar.

Uso:
    python -m scripts.audit_corpus
    python -m scripts.audit_corpus --json
    python -m scripts.audit_corpus --verbose      # lista las fuentes no servidas
"""
from __future__ import annotations

import argparse
import json
import logging
from collections import Counter

from app.config import get_settings
from app.db.models import InterpretationSource
from scripts.research.common import get_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

INTERPRETATIONS = "interpretations_v1"
ROBE_VOICE = "robe_voice_v1"

# kinds que `fetch_sources_for_entity` NO mira (ver scripts/seo/common.py).
ENTITY_EXCLUDED = {"genius_annotation"}
# kinds que viven en el corpus de voz y se recuperan por robe_voice_v1, no por
# interpretations_v1: para ellos el enlace a canción es irrelevante.
VOICE_KINDS = {"robe_quote", "robe_prose", "robe_interview", "about_robe"}


def _qdrant():
    from qdrant_client import QdrantClient

    return QdrantClient(url=get_settings().qdrant_url, check_compatibility=False)


def _scroll_payloads(q, collection: str) -> list[dict]:
    """Todos los payloads de una colección (sin vectores)."""
    out: list[dict] = []
    offset = None
    while True:
        pts, offset = q.scroll(
            collection, limit=1000, offset=offset, with_payload=True, with_vectors=False
        )
        out += [p.payload or {} for p in pts]
        if offset is None:
            return out


def audit() -> dict:
    q = _qdrant()
    names = {c.name for c in q.get_collections().collections}

    interp = _scroll_payloads(q, INTERPRETATIONS) if INTERPRETATIONS in names else []
    voice = _scroll_payloads(q, ROBE_VOICE) if ROBE_VOICE in names else []

    # source_id → tiene algún chunk con song_ids / tiene algún chunk indexado.
    # `vectorize_consensus` mete en esta MISMA colección los consensos destilados con
    # `source_id` negativo (-song_id): no son fuentes del corpus y contarlos infla el
    # total de «con song_ids» (145 puntos en producción, que es justo la diferencia
    # entre creer que hay 275 fuentes irrecuperables y las 420 que hay de verdad).
    con_songids: set[int] = set()
    indexados: set[int] = set()
    consensos = 0
    for p in interp:
        sid = p.get("source_id")
        if not isinstance(sid, int):
            continue
        if sid < 0 or (p.get("kind") or "") == "fan_consensus":
            consensos += 1
            continue
        indexados.add(sid)
        if p.get("song_ids"):
            con_songids.add(sid)

    voice_sids = {p["source_id"] for p in voice if isinstance(p.get("source_id"), int)}

    with get_session() as db:
        rows = db.query(
            InterpretationSource.id,
            InterpretationSource.kind,
            InterpretationSource.title,
            InterpretationSource.referenced_song_ids,
            InterpretationSource.content_clean,
        ).all()

    por_kind: dict[str, Counter] = {}
    no_servidas: list[dict] = []
    for sid, kind, title, refs, clean in rows:
        c = por_kind.setdefault(kind, Counter())
        c["total"] += 1
        if not clean:
            c["sin_contenido"] += 1
        if not refs:
            c["sin_cancion"] += 1
        if sid in indexados:
            c["indexada"] += 1
        if sid in voice_sids:
            c["en_voz"] += 1

        # ¿Puede recuperarla alguien? Solo cuentan los caminos DETERMINISTAS: los
        # dos vectoriales y el de song_ids. El ILIKE por entidad NO cuenta como
        # camino propio —es un potencial, depende de que la fuente nombre a una
        # entidad justo como está escrita en el catálogo— y además ignora
        # `genius_annotation`. Se reporta aparte, no como red de seguridad.
        via_songids = sid in con_songids
        via_semantica = sid in indexados and bool(clean)
        via_voz = sid in voice_sids
        if via_songids:
            c["via_songids"] += 1
        if via_semantica:
            c["via_semantica"] += 1
        if via_voz:
            c["via_voz"] += 1
        if kind in ENTITY_EXCLUDED:
            c["fuera_del_ilike"] += 1
        if not (via_songids or via_semantica or via_voz):
            c["NO_SERVIDA"] += 1
            no_servidas.append({
                "id": sid, "kind": kind, "title": (title or "")[:70],
                "motivo": "sin contenido" if not clean else "no vectorizada",
            })

    return {
        "colecciones": {n: q.get_collection(n).points_count for n in sorted(names)},
        "por_kind": {k: dict(v) for k, v in por_kind.items()},
        "no_servidas": no_servidas,
        "totales": {
            "fuentes": len(rows),
            "indexadas": len(indexados & {r[0] for r in rows}),
            "con_songids": len(con_songids),
            "no_servidas": len(no_servidas),
            "chunks_de_consenso": consensos,
        },
    }


def _print(report: dict, verbose: bool) -> None:
    print("=== COLECCIONES QDRANT ===")
    for n, c in report["colecciones"].items():
        print(f"  {n:22s} {c:>8} puntos")

    print("\n=== CORPUS POR KIND ===")
    cols = ("total", "sin_cancion", "via_songids", "via_semantica", "via_voz",
            "fuera_del_ilike", "NO_SERVIDA")
    print(f"{'kind':20s}" + "".join(f"{c:>16s}" for c in cols))
    for kind, c in sorted(report["por_kind"].items(), key=lambda x: -x[1]["total"]):
        print(f"{kind:20s}" + "".join(f"{c.get(col, 0):>16}" for col in cols))
    print(
        "\n  sin_cancion     = referenced_song_ids vacío → invisible para el boost por song_ids\n"
        "  via_semantica   = recuperable por significado (search_interpretations_passages)\n"
        "  fuera_del_ilike = kind que fetch_sources_for_entity no mira\n"
        "  NO_SERVIDA      = ningún camino determinista la alcanza"
    )

    t = report["totales"]
    print(
        f"\nTOTAL: {t['fuentes']} fuentes · {t['indexadas']} indexadas · "
        f"{t['con_songids']} con song_ids · {t['no_servidas']} NO SERVIDAS"
        f"  (+{t['chunks_de_consenso']} chunks de consenso, que no son fuentes)"
    )
    rescatadas = t["indexadas"] - t["con_songids"]
    if rescatadas > 0:
        print(
            f"Rescatadas por el camino semántico: {rescatadas} fuentes indexadas sin "
            "song_ids, que antes ningún retrieval podía devolver."
        )
    if report["no_servidas"]:
        print(f"\n=== NO SERVIDAS ({len(report['no_servidas'])}) ===")
        muestra = report["no_servidas"] if verbose else report["no_servidas"][:15]
        for s in muestra:
            print(f"  · [{s['kind']}] #{s['id']} {s['title']}")
        if not verbose and len(report["no_servidas"]) > 15:
            print(f"  … y {len(report['no_servidas']) - 15} más (--verbose para verlas)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="Salida JSON en vez de tabla.")
    ap.add_argument("--verbose", action="store_true", help="Lista TODAS las no servidas.")
    args = ap.parse_args()

    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print(report, args.verbose)


if __name__ == "__main__":
    main()
