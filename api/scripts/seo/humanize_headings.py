"""Headings humanos en fichas ya publicadas (criterio de David, 10-11-2026).

Solo cambian las líneas `## `; el resto del cuerpo queda idéntico. Cada heading
pasa `seo_style.heading_verdict` y `ranking_guard` (sin perder búsquedas
protegidas de GSC). Por defecto es un ensayo que imprime un JSON por página.

    python -m scripts.seo.humanize_headings --pages person:paco-doniga,song:la-carrera
    python -m scripts.seo.humanize_headings --sample 10            # las peores, variadas
    python -m scripts.seo.humanize_headings --pages ... --apply    # guarda revisión y aplica

v2 (12-11-2026), que cubre también los posts del blog (la v1 solo miraba fichas):

    python -m scripts.seo.humanize_headings --auditar > auditoria.json
    python -m scripts.seo.humanize_headings --aprobados tanda.jsonl [--apply]

`--aprobados`: una línea JSON por página, {"pagina": "song:x" | "post:x",
"cambios": [{"antes": "…", "despues": "…"}]}. Cambia SOLO esas líneas `## `, con
el texto exacto, y revalida: guarda de headings sobre la página entera, cobertura
de las consultas protegidas y que el resto del cuerpo quede idéntico.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re

from openai import OpenAI

from app.db.models import (
    Album,
    Artist,
    Band,
    Concept,
    ContentRevision,
    Person,
    Place,
    Post,
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


# Temas y conceptos se llaman con un nombre común: se reconocen por la raíz.
NOMBRE_COMUN = frozenset({"theme", "concept"})


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


REASON_V2 = "headings humanos v2 (aprobado)"


def _todas(db) -> list[tuple[str, object, str, str, bool]]:
    """(clave, fila, sujeto, ruta, nombre_común) de fichas y posts publicados."""
    out = []
    for sc, ent in _objetivos(db, None, None):
        sujeto, ruta = sujeto_y_ruta(ent, sc.entity_type)
        out.append((f"{sc.entity_type}:{sc.slug}", sc, sujeto, ruta,
                    sc.entity_type in NOMBRE_COMUN))
    for post in db.query(Post).filter(Post.status == "published").all():
        out.append((f"post:{post.slug}", post, "", f"/blog/{post.slug}", False))
    return out


def auditar(db) -> dict:
    filas = []
    for clave, fila, sujeto, ruta, comun in _todas(db):
        hs = headings.extraer(fila.body_md or "")
        v = seo_style.heading_verdict(hs, subject=sujeto, comun=comun)
        if v.motivos:
            filas.append({"pagina": clave, "ruta": ruta, "sujeto": sujeto, "headings": hs,
                          "problemas": v.motivos})
    return {"con_fallo": len(filas), "filas": filas}


def aplicar_aprobados(db, fichero: str, gsc: dict, apply: bool) -> list[str]:
    from pathlib import Path

    por_clave = {c: (f, s, r, co) for c, f, s, r, co in _todas(db)}
    rutas = []
    for linea in Path(fichero).read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        a = json.loads(linea)
        clave = a["pagina"]
        if clave not in por_clave:
            print(json.dumps({"pagina": clave, "error": "no está publicada"}, ensure_ascii=False))
            continue
        fila, sujeto, ruta, comun = por_clave[clave]
        antes_md = fila.body_md or ""
        nuevo_md, motivos = antes_md, []
        protegidas = ranking_guard.consultas_protegidas(gsc.get(ruta) or [])
        alias = frozenset(seo_style.content_tokens(sujeto)) if sujeto else frozenset()
        for c in a["cambios"]:
            viejo, nuevo = f"## {c['antes'].strip()}", f"## {c['despues'].strip()}"
            if len(re.findall(rf"^{re.escape(viejo)}[ \t]*$", nuevo_md, re.M)) != 1:
                motivos.append(f"«{c['antes']}» no está una sola vez como H2")
                continue
            r = ranking_guard.renombre_permitido(c["antes"], c["despues"], protegidas,
                                                 sujeto=alias)
            if not r.ok:
                motivos.append(f"«{c['antes']}» → «{c['despues']}» pierde una búsqueda protegida")
                continue
            nuevo_md = re.sub(rf"^{re.escape(viejo)}[ \t]*$", lambda _m, n=nuevo: n,
                              nuevo_md, count=1, flags=re.M)
        v = seo_style.heading_verdict(headings.extraer(nuevo_md), subject=sujeto, comun=comun)
        motivos += v.motivos
        if not headings.solo_cambian_headings(antes_md, nuevo_md):
            motivos.append("cambiaría algo más que los headings")
        aplicado = False
        if apply and not motivos and nuevo_md != antes_md:
            es_post = clave.startswith("post:")
            db.add(ContentRevision(target_kind="post" if es_post else "seo_content",
                                   target_id=fila.id, path=ruta, body_md=antes_md,
                                   meta_title=fila.meta_title,
                                   meta_description=fila.meta_description,
                                   h1=fila.title if es_post else fila.h1, reason=REASON_V2))
            fila.body_md = nuevo_md
            db.commit()
            rutas.append(ruta)
            aplicado = True
        print(json.dumps({"pagina": clave, "cambios": a["cambios"], "motivos": motivos,
                          "aplicado": aplicado}, ensure_ascii=False), flush=True)
    return rutas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", help="entity_type:slug separados por comas")
    ap.add_argument("--auditar", action="store_true", help="v2: todo lo que falla")
    ap.add_argument("--aprobados", help="v2: JSONL con el texto exacto aprobado")
    ap.add_argument("--sample", type=int)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    pages = [p.strip() for p in args.pages.split(",")] if args.pages else None
    if args.auditar:
        with SessionLocal() as db:
            json.dump(auditar(db), __import__("sys").stdout, ensure_ascii=False, indent=1)
        return
    if args.aprobados:
        gsc, _ = load_gsc_pages()
        with SessionLocal() as db:
            rutas = aplicar_aprobados(db, args.aprobados, gsc, args.apply)
        if rutas:
            from app.services.publishing import revalidate_paths
            revalidate_paths(rutas)
        return
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    gsc, _ = load_gsc_pages()
    rutas = []
    with SessionLocal() as db:
        for sc, ent in _objetivos(db, pages, args.sample):
            sujeto, ruta = sujeto_y_ruta(ent, sc.entity_type)
            protegidas = ranking_guard.consultas_protegidas(gsc.get(ruta) or [])
            prop = headings.proponer(client, body_md=sc.body_md, subject=sujeto,
                                     protegidas=protegidas,
                                     comun=sc.entity_type in NOMBRE_COMUN)
            aplicado = False
            if args.apply and prop.aplicable:
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
