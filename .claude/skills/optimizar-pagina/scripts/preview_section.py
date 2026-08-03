"""Imprime la sección que augment_deep AÑADIRÍA, sin tocar la BD.

    docker cp .claude/skills/optimizar-pagina/scripts/preview_section.py \
              robelyrics-api:/tmp/preview_section.py
    docker compose exec -T -e PYTHONPATH=/app api python /tmp/preview_section.py \
        --asset album:agila --hint "la portada: quién la ilustró"

Existe porque el gate anti-paja solo bloquea si el rigor BAJA: un bloque que no
mejora nada pasa igual. Hay que leerlo antes de publicar.
"""
import argparse
import sys
sys.path.insert(0,'/app')
from openai import OpenAI
from sqlalchemy import select
from app.config import get_settings
from app.db.session import SessionLocal
from app.db.models import Album
from scripts.seo.augment_deep import augment_entity
ap=argparse.ArgumentParser()
ap.add_argument("--asset", default="album:agila", help="tipo:slug")
ap.add_argument("--hint", default=None)
args=ap.parse_args()
_, slug = args.asset.split(":",1)

db=SessionLocal()
a=db.execute(select(Album).where(Album.slug==slug)).scalar_one()
c=OpenAI(api_key=get_settings().openai_api_key)
r=augment_entity(db,c,'album',a,gap_hint=args.hint)
print("=== RIGOR:",r.get('rigor'),"· grew:",r.get('grew'),"· noop:",r.get('noop'))
if not r or r.get("noop"):
    print("=== no-op: nada verificable que añadir ===")
    raise SystemExit(0)
print("=== SECCIÓN NUEVA (NO publicada) ===")
# Diff por líneas: el slice por longitud ensucia la salida porque
# normalize_headings puede haber reescrito los headings del texto previo.
antes=set(r["before"].splitlines())
print("\n".join(l for l in r["after"].splitlines() if l not in antes).strip())
