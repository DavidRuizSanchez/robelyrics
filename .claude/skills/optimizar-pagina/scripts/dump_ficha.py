"""Vuelca la ficha REAL de una página (la de producción) para poder editarla.

    docker cp .../dump_ficha.py <cont>:/tmp/ && \
    docker compose ... exec -T -e PYTHONPATH=/app api python /tmp/dump_ficha.py \
        --asset album:agila > ficha.json

Se saca de producción a propósito: la BD local suele estar desfasada. Medido el
03-08-2026 — local tenía 159 fichas del generador viejo y prod solo 3.
"""
import argparse, json, sys
sys.path.insert(0, "/app")
from sqlalchemy import select
from app.db.session import SessionLocal
from app.db.models import Album, Artist, SeoContent, Song

ap = argparse.ArgumentParser()
ap.add_argument("--asset", required=True, help="tipo:slug")
a = ap.parse_args()
tipo, slug = a.asset.split(":", 1)

db = SessionLocal()
MODELO = {"album": Album, "song": Song, "artist": Artist}[tipo]
ent = db.execute(select(MODELO).where(MODELO.slug == slug)).scalar_one()
c = db.execute(select(SeoContent).where(
    SeoContent.entity_type == tipo, SeoContent.entity_id == ent.id)).scalar_one()

print(json.dumps({
    "asset": a.asset, "entity_id": ent.id,
    "meta_title": c.meta_title, "meta_description": c.meta_description,
    "target_keyword": c.target_keyword, "secondary": c.secondary_keywords,
    "published": c.published, "sources_count": c.sources_count,
    "palabras": len((c.body_md or "").split()),
    "body": c.body_md,
}, ensure_ascii=False, indent=1))
