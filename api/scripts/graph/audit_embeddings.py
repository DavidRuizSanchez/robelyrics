"""Audita la cobertura de embeddings: lista el material útil que NO está
vectorizado. Lo usa el cron de frescura para alertar de huecos.

Uso: python -m scripts.graph.audit_embeddings
"""
from __future__ import annotations

from sqlalchemy import func

from app.db.models import Band, InterpretationSource, Person
from app.db.session import SessionLocal
from app.services.qdrant_client import get_qdrant
from scripts.seo.common import log


def _covered_source_ids(q) -> set[int]:
    covered: set[int] = set()
    for coll in ("interpretations_v1", "robe_voice_v1"):
        try:
            off = None
            while True:
                pts, off = q.scroll(collection_name=coll, limit=1000, offset=off,
                                    with_payload=["source_id"], with_vectors=False)
                for p in pts:
                    sid = (p.payload or {}).get("source_id")
                    if sid is not None:
                        covered.add(int(sid))
                if off is None:
                    break
        except Exception:  # noqa: BLE001
            pass
    return covered


def main() -> None:
    db = SessionLocal()
    q = get_qdrant()
    covered = _covered_source_ids(q)
    with_content = {
        i for (i,) in db.query(InterpretationSource.id)
        .filter(func.length(InterpretationSource.content_clean) > 200).all()
    }
    missing = with_content - covered
    log(f"interpretation_sources con contenido: {len(with_content)} · embebidas: "
        f"{len(with_content & covered)} · SIN cubrir: {len(missing)}",
        "warn" if missing else "ok")

    # Colecciones que cubren bio_long (entities_v1) y posts (posts_v1).
    try:
        names = {c.name for c in q.get_collections().collections}
        ent_pts = q.get_collection("entities_v1").points_count if "entities_v1" in names else 0
    except Exception:  # noqa: BLE001
        ent_pts = 0
    bios = (db.query(func.count()).filter(func.length(Person.bio_long) > 200).scalar()
            + db.query(func.count()).filter(func.length(Band.bio_long) > 200).scalar())
    log(f"bio_long (person+band): {bios} entidades · entities_v1: {ent_pts} puntos",
        "warn" if (bios and ent_pts == 0) else "ok")

    if missing:
        log("→ re-embebe fan-content: python -m scripts.research.embed_interpretations", "warn")
    if bios and ent_pts == 0:
        log("→ vectoriza bios: python -m scripts.graph.embed_entity_bios", "warn")


if __name__ == "__main__":
    main()
