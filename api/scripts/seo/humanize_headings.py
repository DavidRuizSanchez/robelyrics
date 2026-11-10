"""Headings humanos en fichas ya publicadas (criterio de David, 10-11-2026).

Solo cambian las líneas `## `; el resto del cuerpo queda idéntico. Cada heading
pasa `seo_style.heading_verdict` y `ranking_guard` (sin perder búsquedas
protegidas de GSC). Por defecto es un ensayo que imprime un JSON por página.

    python -m scripts.seo.humanize_headings --pages person:paco-doniga,song:la-carrera
    python -m scripts.seo.humanize_headings --sample 10            # las peores, variadas
    python -m scripts.seo.humanize_headings --pages ... --apply    # guarda revisión y aplica
"""
from __future__ import annotations

import argparse
import json
import logging
import os

from openai import OpenAI

from app.db.models import (
    Album,
    Artist,
    Band,
    Concept,
    ContentRevision,
    Person,
    Place,
    SeoContent,
    Song,
    Theme,
)
from app.db.session import SessionLocal
from app.services import headings, ranking_guard, seo_style
from app.services.content_placement import load_gsc_pages

logging.basicConfig(level=logging.WARNING)

_MODELOS = {"person": Person, "album": Album, "song": Song, "artist": Artist, "place": Place,
            "band": Band, "theme": Theme, "concept": Concept}
_PREFIJO = {"person": "personas", "place": "lugares", "theme": "temas", "concept": "conceptos"}


def sujeto_y_ruta(ent, entity_type: str) -> tuple[str, str]:
    nombre = (getattr(ent, "stage_name", None) or getattr(ent, "title", None)
              or getattr(ent, "name", None) or getattr(ent, "full_name", None) or ent.slug)
    if entity_type == "song":
        ruta = f"/{ent.album.artist.slug}/{ent.album.slug}/{ent.slug}"
    elif entity_type == "album":
        ruta = f"/{ent.artist.slug}/{ent.slug}"
    elif entity_type == "artist":
        ruta = f"/{ent.slug}"
    elif entity_type == "band":
        ruta = f"/{'sellos' if getattr(ent, 'kind', '') == 'label' else 'grupos'}/{ent.slug}"
    else:
        ruta = f"/{_PREFIJO[entity_type]}/{ent.slug}"
    return nombre, ruta


def _objetivos(db, pages: list[str] | None, sample: int | None) -> list[tuple[SeoContent, object]]:
    filas = db.query(SeoContent).filter(SeoContent.published.is_(True)).all()
    out = []
    for sc in filas:
        modelo = _MODELOS.get(sc.entity_type)
        if modelo is None:
            continue
        if pages is not None and f"{sc.entity_type}:{sc.slug}" not in pages:
            continue
        ent = db.get(modelo, sc.entity_id)
        if ent is not None:
            out.append((sc, ent))
    if sample:
        # Las que más bloquean, repartidas por tipo (muestra antes del set completo).
        def peso(par):
            sc, ent = par
            v = seo_style.heading_verdict(headings.extraer(sc.body_md), subject=sujeto_y_ruta(
                ent, sc.entity_type)[0])
            return len(v.motivos) * 10 + len(v.avisos)
        malos = sorted((p for p in out if peso(p) > 0), key=peso, reverse=True)
        tipos, elegidos = ("person", "song", "band", "album", "place", "artist"), []
        while len(elegidos) < sample and malos:
            for t in tipos:
                cand = next((p for p in malos if p[0].entity_type == t and p not in elegidos), None)
                if cand and len(elegidos) < sample:
                    elegidos.append(cand)
            if all(next((p for p in malos if p[0].entity_type == t and p not in elegidos), None)
                   is None for t in tipos):
                break
        out = elegidos
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", help="entity_type:slug separados por comas")
    ap.add_argument("--sample", type=int)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    pages = [p.strip() for p in args.pages.split(",")] if args.pages else None
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    gsc, _ = load_gsc_pages()
    rutas = []
    with SessionLocal() as db:
        for sc, ent in _objetivos(db, pages, args.sample):
            sujeto, ruta = sujeto_y_ruta(ent, sc.entity_type)
            protegidas = ranking_guard.consultas_protegidas(gsc.get(ruta) or [])
            prop = headings.proponer(client, body_md=sc.body_md, subject=sujeto,
                                     protegidas=protegidas)
            aplicado = False
            if args.apply and prop.cambia and not prop.veredicto_despues_bloquea:
                db.add(ContentRevision(target_kind="seo_content", target_id=sc.id, path=ruta,
                                       body_md=sc.body_md, meta_title=sc.meta_title,
                                       meta_description=sc.meta_description, h1=sc.h1,
                                       reason="headings humanos (humanize_headings)"))
                sc.body_md = prop.body_nuevo
                db.commit()
                rutas.append(ruta)
                aplicado = True
            print(json.dumps({"pagina": f"{sc.entity_type}:{sc.slug}", "ruta": ruta,
                              "sujeto": sujeto, "antes": prop.antes, "despues": prop.despues,
                              "problemas_antes": prop.veredicto_antes,
                              "problemas_despues": prop.veredicto_despues,
                              "mantenidos_por_ranking": prop.mantenidos,
                              "protegidas": len(protegidas), "aplicado": aplicado},
                             ensure_ascii=False), flush=True)
    if rutas:
        from app.services.publishing import revalidate_paths
        revalidate_paths(rutas)


if __name__ == "__main__":
    main()
