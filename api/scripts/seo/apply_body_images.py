"""Inserta las fotos de `data/body_images.yaml` en el cuerpo de sus fichas.

En seco por defecto: dice qué haría con cada foto. Con --apply guarda la página
entera en `content_revisions` (para poder revertir), escribe y revalida.

    python -m scripts.seo.apply_body_images [--apply]
"""
from __future__ import annotations

import argparse
import json

from app.db.models import ContentRevision, SeoContent
from app.db.session import SessionLocal
from app.services import body_images


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    rutas = []
    with SessionLocal() as db:
        for e in body_images.cargar():
            tipo, _, slug = (e.get("target") or "").partition(":")
            sc = (db.query(SeoContent)
                  .filter(SeoContent.entity_type == tipo, SeoContent.slug == slug).first())
            if sc is None:
                print(json.dumps({"target": e.get("target"), "estado": "sin_ficha"}))
                continue
            r = body_images.preparar(e, sc.body_md)
            if args.apply and r.estado == "insertada":
                ruta = {"person": "/personas/", "place": "/lugares/"}.get(tipo, f"/{tipo}/") + slug
                db.add(ContentRevision(target_kind="seo_content", target_id=sc.id, path=ruta,
                                       body_md=sc.body_md, meta_title=sc.meta_title,
                                       meta_description=sc.meta_description, h1=sc.h1,
                                       reason=f"foto en el cuerpo: {e.get('alt', '')[:80]}"))
                sc.body_md = r.body_nuevo
                db.commit()
                rutas.append(ruta)
            print(json.dumps({"target": r.target, "estado": r.estado, "motivo": r.motivo,
                              "aplicado": bool(args.apply and r.estado == "insertada")},
                             ensure_ascii=False), flush=True)
    if rutas:
        from app.services.publishing import revalidate_paths
        revalidate_paths(rutas)


if __name__ == "__main__":
    main()
