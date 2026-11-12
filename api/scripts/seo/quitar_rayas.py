"""Quita la raya larga («—», «―») de lo YA publicado (David, 12-11-2026).

Desde este cambio el listener del ORM (`models._make_name_policy_listener`) la
quita en cada escritura; esto barre lo que se escribió antes. Recorre:

- `seo_content` y `posts`: body, title/h1, metas, excerpt y los JSONB;
- `related_videos.title` y `songs.youtube_title` (títulos de vídeo: « - »).

Solo cambian las rayas: se comprueba campo a campo que, quitando rayas, comas y
espacios, el texto es idéntico. Si no, ese campo no se toca y sale en el informe.
Antes de escribir una página guarda `content_revisions` (reason «sin rayas»); los
títulos de vídeo, que no tienen revisiones, van a un JSON de copia.

    python -m scripts.seo.quitar_rayas                  (ensayo: resumen + muestra)
    python -m scripts.seo.quitar_rayas --apply
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from app.db.models import ContentRevision, Post, RelatedVideo, SeoContent, Song
from app.db.session import SessionLocal
from app.services.link_policy import rutas_de_nodos
from app.services.text_sanitizer import quitar_rayas

REASON = "sin rayas (quitar_rayas 12-11-2026)"
COPIA = Path("/tmp/quitar_rayas_copia.json")
_SEO = ("body_md", "meta_title", "meta_description", "h1", "schema_jsonld", "entities")
_POST = ("body_md", "title", "excerpt", "meta_title", "meta_description")


def _esqueleto(s: str) -> str:
    """El texto sin lo que `quitar_rayas` puede tocar: si coincide antes y
    después, solo han cambiado rayas (y la puntuación que las sustituye)."""
    return re.sub(r"[—―,\s\-]", "", s)


def _limpio(valor, *, titulo: bool = False):
    if isinstance(valor, str):
        return quitar_rayas(valor, titulo=titulo)
    if isinstance(valor, (dict, list)):
        raw = json.dumps(valor, ensure_ascii=False)
        nuevo = quitar_rayas(raw)
        return json.loads(nuevo) if nuevo != raw else valor
    return valor


def _texto(v) -> str:
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--muestra", type=int, default=8)
    args = ap.parse_args()

    informe = {"paginas": 0, "campos": 0, "videos": 0, "titulos_youtube": 0,
               "rechazados": [], "aplicado": args.apply}
    muestra, copia, revalidar = [], {"related_videos": {}, "songs": {}}, []
    with SessionLocal() as db:
        rutas = rutas_de_nodos(db)
        filas = [("post", p, _POST, f"/blog/{p.slug}") for p in db.query(Post).all()]
        filas += [("seo_content", s, _SEO, rutas.get((s.entity_type, s.entity_id), ""))
                  for s in db.query(SeoContent).all()]
        for kind, row, campos, ruta in filas:
            cambios = {}
            for f in campos:
                v = getattr(row, f, None)
                nuevo = _limpio(v)
                if nuevo is v or nuevo == v:
                    continue
                if _esqueleto(_texto(v)) != _esqueleto(_texto(nuevo)):
                    informe["rechazados"].append(f"{kind}:{row.slug}:{f}")
                    continue
                cambios[f] = nuevo
            if not cambios:
                continue
            informe["paginas"] += 1
            informe["campos"] += len(cambios)
            if len(muestra) < args.muestra and "body_md" in cambios:
                antes = row.body_md
                for m in re.finditer(r".{0,60}[—―].{0,60}", antes):
                    muestra.append({"pagina": f"{kind}:{row.slug}", "antes": m.group(0)})
                    break
            if args.apply:
                db.add(ContentRevision(
                    target_kind=kind, target_id=row.id, path=ruta,
                    body_md=row.body_md, meta_title=row.meta_title,
                    meta_description=row.meta_description,
                    h1=getattr(row, "h1", None) if kind == "seo_content" else row.title,
                    reason=REASON,
                ))
                for f, nuevo in cambios.items():
                    setattr(row, f, nuevo)
                db.commit()
                if ruta:
                    revalidar.append(ruta)

        for v in db.query(RelatedVideo).all():
            nuevo = quitar_rayas(v.title, titulo=True)
            if nuevo != v.title:
                informe["videos"] += 1
                copia["related_videos"][v.id] = v.title
                if args.apply:
                    v.title = nuevo
        for s in db.query(Song).filter(Song.youtube_title.isnot(None)).all():
            nuevo = quitar_rayas(s.youtube_title, titulo=True)
            if nuevo != s.youtube_title:
                informe["titulos_youtube"] += 1
                copia["songs"][s.id] = s.youtube_title
                if args.apply:
                    s.youtube_title = nuevo
        if args.apply:
            db.commit()

    COPIA.write_text(json.dumps(copia, ensure_ascii=False, indent=1))
    informe["copia_titulos_de_video"] = str(COPIA)
    print(json.dumps(informe, ensure_ascii=False, indent=1))
    for m in muestra:
        print(json.dumps(m, ensure_ascii=False))
    if args.apply and (revalidar or informe["videos"] or informe["titulos_youtube"]):
        from app.services.publishing import revalidate_paths

        # Los vídeos salen en muchas fichas: se vacía la caché entera.
        revalidate_paths(revalidar, layouts=["/"])


if __name__ == "__main__":
    main()
