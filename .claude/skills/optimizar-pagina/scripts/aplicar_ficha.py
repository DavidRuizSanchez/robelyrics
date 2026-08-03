"""Aplica un body_md editado a mano, tras pasar los gates. NO publica a ciegas.

    docker compose ... exec -T -e PYTHONPATH=/app api python /tmp/aplicar_ficha.py \
        --asset album:agila --body /tmp/nuevo.md \
        --title "..." --desc "..." --secundarias "kw1,kw2"

Aborta si el gate de no-pérdida rechaza. Guarda copia del cuerpo anterior en
/tmp/<slug>_backup.md antes de escribir.
"""
import argparse
import os
import re
import sys
sys.path.insert(0, "/app")
os.environ["SEO_KEEP_PUBLISHED"] = "1"   # la página no se cae mientras se aplica
from sqlalchemy import select, update
from app.db.session import SessionLocal
from app.db.models import Album, Artist, SeoContent, Song
from app.services.content_guard import find_especulacion, no_loss_verdict
from scripts.seo.common import upsert_seo_content

ap = argparse.ArgumentParser()
ap.add_argument("--asset", required=True)
ap.add_argument("--body", required=True)
ap.add_argument("--title")
ap.add_argument("--desc")
ap.add_argument("--secundarias", default="")
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()
tipo, slug = args.asset.split(":", 1)

nuevo = open(args.body, encoding="utf-8").read()
db = SessionLocal()
MODELO = {"album": Album, "song": Song, "artist": Artist}[tipo]
ent = db.execute(select(MODELO).where(MODELO.slug == slug)).scalar_one()
c = db.execute(select(SeoContent).where(
    SeoContent.entity_type == tipo, SeoContent.entity_id == ent.id)).scalar_one()

# Los cortes del propio disco NO cuentan como pérdida: la plantilla ya pinta la
# sección «Canciones» con el tracklist entero enlazado (web/app/[artist]/[album]/
# page.tsx), así que repetirlo en la prosa lo duplica en pantalla. Es el mismo
# criterio que `content_guard` documenta y el que aplica `relink_existing`.
propios = {u for u in re.findall(r"\]\((\S+?)\)", c.body_md or "")
           if re.sub(r"^https?://[^/]+", "", u).startswith(f"/{slug}/")
           or f"/{slug}/" in re.sub(r"^https?://[^/]+", "", u)}

v = no_loss_verdict(c.body_md, nuevo, exempt_links=frozenset(propios))
if propios:
    print(f"exentos {len(propios)} enlace(s) a cortes del propio disco")
print("gate no-pérdida:", v.resumen())
if not v.ok:
    print("ABORTADO: la ficha NO se toca")
    raise SystemExit(1)
esp = find_especulacion(nuevo)
if esp:
    print("ABORTADO: el texto nuevo especula →", esp)
    raise SystemExit(1)
if args.dry_run:
    print("dry-run: no se escribe")
    raise SystemExit(0)

open(f"/tmp/{slug}_backup.md", "w", encoding="utf-8").write(c.body_md)
upsert_seo_content(db, entity_type=tipo, entity_id=ent.id, slug=slug,
                   body_md=nuevo,
                   meta_title=(args.title or c.meta_title or "")[:60],
                   meta_description=(args.desc or c.meta_description or "")[:155],
                   schema_jsonld=c.schema_jsonld, entities=c.entities or [],
                   force=True)
sec = [s.strip() for s in args.secundarias.split(",") if s.strip()]
if sec:
    db.execute(update(SeoContent)
               .where(SeoContent.entity_type == tipo, SeoContent.entity_id == ent.id)
               .values(secondary_keywords=[{"keyword": k} for k in sec]))
db.commit()
print(f"APLICADO · backup en /tmp/{slug}_backup.md")
