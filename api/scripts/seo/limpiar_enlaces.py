"""Limpia el enlazado de lo YA publicado con las reglas de `link_policy` (11-11-2026).

Solo quita ENLACES; el texto se queda byte a byte (`solo_cambian_enlaces`, que
se comprueba página a página: si falla, esa página no se toca). Motivos:
`plantilla`, `repetido` (se queda el primero), `propia`, `sin_relacion`
(taxonomía sin arista en el grafo) y `tope` (más de 3: se quedan los de más
relevancia, con el mismo criterio que el autolinker).

Después del recorte, COMPLETA hasta el tope con el autolinker (mismo contexto),
para que la operación revisada sea una sola: el relinker del domingo queda en
punto fijo y no añade nada por su cuenta. Lo añadido sale en el CSV con motivo
`añadido`.

Antes de escribir guarda la página entera en `content_revisions` (reason
"limpieza de enlaces"), que es lo que usa «revertir».

    python -m scripts.seo.limpiar_enlaces                       (ensayo: resumen + CSV)
    python -m scripts.seo.limpiar_enlaces --muestra 10          (ensayo + 10 páginas detalladas)
    python -m scripts.seo.limpiar_enlaces --pages person:alen-ayerdi,post:mi-post --apply
    python -m scripts.seo.limpiar_enlaces --apply               (todo)
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
from collections import Counter
from pathlib import Path

from app.db.models import ContentRevision, Post, SeoContent
from app.db.session import SessionLocal
from app.services.entity_resolver import (
    _url_path,
    autolink_corpus,
    build_corpus_index,
    load_anchor_stats,
    load_link_stats,
)
from app.services.link_policy import (
    ENLACE,
    cargar_relaciones,
    contexto_de,
    contexto_post,
    presupuesto,
    norm_path,
    recortar,
    rutas_de_nodos,
    solo_cambian_enlaces,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REASON = "limpieza de enlaces (link_policy 11-11-2026)"
CSV_PATH = Path("/tmp/limpiar_enlaces.csv")


def _objetivos(db, pages: list[str] | None):
    filtro = None
    if pages:
        filtro = {tuple(p.split(":", 1)) for p in pages}
    for p in db.query(Post).filter(Post.body_md.isnot(None)).order_by(Post.id):
        if filtro is None or ("post", p.slug) in filtro:
            yield "post", p
    for s in db.query(SeoContent).filter(SeoContent.body_md.isnot(None)).order_by(SeoContent.id):
        if filtro is None or (s.entity_type, s.slug) in filtro:
            yield "seo_content", s


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", help="tipo:slug separados por comas (post:slug, person:slug…)")
    ap.add_argument("--muestra", type=int, default=0, help="páginas a detallar en el ensayo")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--csv", default=str(CSV_PATH), help="dónde escribir el detalle")
    ap.add_argument("--volcar-plantillas", help="JSON {ruta: plantilla calculada}, para auditarla")
    args = ap.parse_args()
    pages = [p.strip() for p in args.pages.split(",")] if args.pages else None

    with SessionLocal() as db:
        indice = build_corpus_index(db)
        tipo_de: dict[str, str] = {}
        nombres_de: dict[str, list[str]] = {}
        for e in indice:
            p = _url_path(e["url"])
            tipo_de.setdefault(p, e["type"])
            nombres_de.setdefault(p, []).append(e["name"])
        rutas = rutas_de_nodos(db)
        relaciones = cargar_relaciones(db, rutas)
        stats, anchors = load_link_stats(), load_anchor_stats()

        motivos: Counter[str] = Counter()
        filas, detalle, rechazadas, revalidar = [], [], [], []
        cambiadas = total = 0
        plantillas: dict[str, list[str]] = {}
        no_fijas: list[str] = []
        sobre_tope: list[str] = []
        for kind, row in _objetivos(db, pages):
            total += 1
            if kind == "post":
                ctx = contexto_post(row.slug, relaciones)
            else:
                ctx = contexto_de(db, row.entity_type, row.entity_id, rutas=rutas,
                                  relaciones=relaciones)
            if ctx.origen:
                plantillas[ctx.origen] = sorted(ctx.plantilla)
            r = recortar(row.body_md, ctx, tipo_de=tipo_de, nombres_de=nombres_de)
            final = autolink_corpus(r.md, indice, exclude_slug=row.slug, link_stats=stats,
                                    contexto=ctx, anchor_stats=anchors)
            if final == row.body_md:
                continue
            nombre = f"{'post' if kind == 'post' else row.entity_type}:{row.slug}"
            if not solo_cambian_enlaces(row.body_md, final, permite_nuevos=True):
                rechazadas.append(nombre)
                continue
            # Punto fijo: el relinker del domingo no tiene que encontrar nada.
            otra = autolink_corpus(final, indice, exclude_slug=row.slug, link_stats=stats,
                                   contexto=ctx, anchor_stats=anchors)
            if otra != final:
                no_fijas.append(nombre)
            if presupuesto(final, ctx.plantilla) < 0:
                sobre_tope.append(nombre)
            antes = {(a, norm_path(u)) for a, u in ENLACE.findall(r.md)}
            anadidos = [(a, norm_path(u) or u, "añadido") for a, u in ENLACE.findall(final)
                        if (a, norm_path(u)) not in antes]
            cambiadas += 1
            for anchor, ruta, motivo in r.quitados + anadidos:
                motivos[motivo] += 1
                filas.append([nombre, ctx.origen or "", anchor, ruta, motivo])
            detalle.append({"pagina": nombre, "ruta": ctx.origen, "quitados": r.quitados,
                            "añadidos": anadidos,
                            "quedan": [(a, norm_path(u) or u) for a, u in ENLACE.findall(final)
                                       if norm_path(u)]})
            if args.apply:
                db.add(ContentRevision(
                    target_kind=kind, target_id=row.id, path=ctx.origen or "",
                    body_md=row.body_md, meta_title=row.meta_title,
                    meta_description=row.meta_description,
                    h1=getattr(row, "h1", None), reason=REASON,
                ))
                row.body_md = final
                db.commit()
                if ctx.origen:
                    revalidar.append(ctx.origen)

    if args.volcar_plantillas:
        Path(args.volcar_plantillas).write_text(json.dumps(plantillas, ensure_ascii=False))
    with Path(args.csv).open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pagina", "ruta", "anchor", "destino", "motivo"])
        w.writerows(filas)
    resumen = {"paginas": total, "paginas_que_cambian": cambiadas,
               "enlaces_quitados": sum(v for k, v in motivos.items() if k != "añadido"),
               "enlaces_añadidos": motivos.get("añadido", 0), "por_motivo": dict(motivos),
               "rechazadas_por_invariante": rechazadas, "sin_punto_fijo": no_fijas,
               "por_encima_del_tope": sobre_tope, "aplicado": args.apply,
               "csv": args.csv}
    print(json.dumps(resumen, ensure_ascii=False, indent=1))
    for d in sorted(detalle, key=lambda d: -len(d["quitados"]))[: args.muestra]:
        print(json.dumps(d, ensure_ascii=False))
    if revalidar:
        from app.services.publishing import revalidate_paths

        revalidate_paths(revalidar)


if __name__ == "__main__":
    main()
