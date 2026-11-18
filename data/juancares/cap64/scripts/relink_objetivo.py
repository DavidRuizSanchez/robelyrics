"""Re-enlazado SOLO de las páginas que nombran a las fichas recién publicadas.

Misma lógica que el cron del domingo (`relink_existing._clean`: quita lo que el
autolinker sabe reponer y vuelve a elegir los 4 mejores con link_stats), aplicada a
cinco páginas en vez de a todo el sitio. Lo que el domingo haría igual, adelantado.

Uso: ... python - [--apply] < relink_objetivo.py
"""
import json
import re
import sys

from app.db.models import Post, SeoContent
from app.db.session import SessionLocal
from app.services.entity_resolver import build_corpus_index, load_link_stats
from scripts.seo.relink_existing import _clean, _path

APLICAR = "--apply" in sys.argv
# /lugares/plasencia NO: bajaría de 8 a 4 enlaces quitando los de la fusión recién aprobada
# y no ganaría Brea (ensayo del 10-11-2026). /lugares/extremadura no cambiaba.
FICHAS = [("person", "manolo-chinato")]
POSTS = ["robe-de-chapista-a-icono-del-rock-espanol", "primeras-flores-amarillas-plasencia-cumple-robe-2026"]
_L = re.compile(r"(?<!\!)\[[^\]]+\]\(([^)]+)\)")

with SessionLocal() as db:
    index = build_corpus_index(db)
    stats = load_link_stats()
    paths = {_path(e["url"]) for e in index}
    filas = [("seo", s, s.slug) for s in db.query(SeoContent).filter(
        SeoContent.published.is_(True)).all() if (s.entity_type, s.slug) in FICHAS]
    filas += [("post", p, p.slug) for p in db.query(Post).filter(Post.slug.in_(POSTS)).all()]
    rutas = []
    for tipo, fila, slug in filas:
        nuevo = _clean(fila.body_md, index, stats, exclude_slug=slug if tipo == "seo" else None,
                       index_paths=paths)
        antes = [_path(u) for u in _L.findall(fila.body_md or "")]
        despues = [_path(u) for u in _L.findall(nuevo or "")]
        print(json.dumps({"pagina": f"{tipo}:{slug}", "antes": antes, "despues": despues,
                          "cambia": nuevo != fila.body_md}, ensure_ascii=False))
        if APLICAR and nuevo != fila.body_md:
            fila.body_md = nuevo
            rutas.append(f"/lugares/{slug}" if getattr(fila, "entity_type", "") == "place"
                         else f"/personas/{slug}" if tipo == "seo" else f"/blog/{slug}")
    if APLICAR:
        db.commit()
        from app.services.publishing import revalidate_paths
        revalidate_paths(rutas)
        print(json.dumps({"aplicado": rutas}))
