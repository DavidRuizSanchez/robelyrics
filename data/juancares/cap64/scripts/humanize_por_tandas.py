"""Headings humanos en TODO el sitio, por tandas de tipo (OK de David, 10-11-2026).

Llama a `scripts.seo.humanize_headings` con --apply, un tipo detrás de otro, solo
sobre las páginas cuya guarda falla hoy. Cada línea de salida es el JSON de una página.
"""
import sys

from app.db.models import SeoContent
from app.db.session import SessionLocal
from app.services import headings, seo_style
from scripts.seo import humanize_headings as hh

TANDAS = ["person", "band", "album", "place", "artist", "song", "theme", "concept"]
with SessionLocal() as db:
    por_tipo = {t: [] for t in TANDAS}
    for sc in db.query(SeoContent).filter(SeoContent.published.is_(True)).all():
        modelo = hh._MODELOS.get(sc.entity_type)
        if sc.entity_type not in por_tipo or modelo is None:
            continue
        ent = db.get(modelo, sc.entity_id)
        if ent is None:
            continue
        sujeto, _ = hh.sujeto_y_ruta(ent, sc.entity_type)
        v = seo_style.heading_verdict(headings.extraer(sc.body_md), subject=sujeto)
        if not v.ok or v.avisos:
            por_tipo[sc.entity_type].append(f"{sc.entity_type}:{sc.slug}")
for t in TANDAS:
    paginas = por_tipo[t]
    print(f"# tanda {t}: {len(paginas)} páginas", file=sys.stderr, flush=True)
    if paginas:
        sys.argv = ["humanize_headings", "--pages", ",".join(paginas), "--apply"]
        hh.main()
