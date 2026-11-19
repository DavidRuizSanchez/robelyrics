"""Inventario de historias de un disco, en seco (no escribe ni guarda nada).

    python -m scripts.blog.inventario_historias --album-slug se-nos-lleva-el-aire
"""
from __future__ import annotations

import argparse
import json

from sqlalchemy import select

from app.db.models import Album
from app.db.session import SessionLocal
from app.services.deep_research import _hard_facts, entity_names
from app.services.historias_disco import inventario


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--album-slug", required=True)
    ap.add_argument("--sin-web", action="store_true")
    args = ap.parse_args()
    db = SessionLocal()
    try:
        album = db.execute(select(Album).where(Album.slug == args.album_slug)).scalar_one()
        sujeto, _ = entity_names(db, "album", album)
        hechos = _hard_facts(db, "album", album, sujeto)
        historias = inventario(db, album, hechos_duros=hechos, usar_web=not args.sin_web)
        print(json.dumps([h.to_dict() for h in historias], ensure_ascii=False, indent=1))
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
