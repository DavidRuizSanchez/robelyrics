"""Titles humanos en lo ya publicado (criterio de David, 11-11-2026).

«Plasencia Robe: Cuna de Extremoduro y su legado» no es español. Medido el 11-11:
264 de 361 titles propios con la keyword pegada, una fórmula vacía o Title Case.
Las guardas solo corrían al ESCRIBIR, así que nadie había repasado lo publicado.

Cada title nuevo:
- pasa `seo_style.title_verdict` (pegada, fórmulas, Title Case, sujeto, facetas);
- cubre el `target_keyword` (`cubre_termino`), sin pegarlo;
- cubre TODAS las consultas protegidas de GSC que cubría el title viejo por sí
  solo (`ranking_guard.consultas_protegidas`, volcado de 12 semanas). Si no, no
  se aplica: el title es lo primero que Google cruza con la consulta.

Solo cambia `meta_title`. El H1, el cuerpo y la description quedan igual.
Por defecto es un ensayo que imprime un JSON por página.

    python -m scripts.seo.humanize_titles --sample 10                 # muestra variada
    python -m scripts.seo.humanize_titles --pages place:plasencia,post:mi-slug
    python -m scripts.seo.humanize_titles --exposicion > tandas.json  # orden sin LLM
    python -m scripts.seo.humanize_titles --pages ... --apply         # revisión + aplica

v2 (12-11-2026):

    python -m scripts.seo.humanize_titles --auditar > auditoria.json  # todo lo que falla
    python -m scripts.seo.humanize_titles --aprobados tanda.jsonl     # ensayo
    python -m scripts.seo.humanize_titles --aprobados tanda.jsonl --apply

`--auditar` cubre también el título de los posts (su H1 y el de sus tarjetas),
que la v1 no miraba. `--aprobados` aplica el TEXTO EXACTO que David aprobó, una
línea JSON por cambio: {"pagina": "song:x" | "post:x", "campo": "meta_title" | "h1",
"texto": "…"}. Lo revalida con las mismas guardas y la cobertura de las consultas
protegidas; si algo falla, esa línea no se aplica y sale con su motivo.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass, field

from openai import OpenAI

from app.db.models import ContentRevision, Post, SeoContent
from app.db.session import SessionLocal
from app.services import ranking_guard, seo_style
from app.services.content_placement import load_gsc_pages
from scripts.seo.humanize_headings import _MODELOS, sujeto_y_ruta

logging.basicConfig(level=logging.WARNING)

REASON = "titles humanos (humanize_titles)"
REASON_V2 = "titles humanos v2 (aprobado)"
# Lo que no pasa por aquí: las páginas que viven en código (/robe, /blog, hubs) van
# en su propio PR, y `/personas` es plantilla con sufijo de marca.
_SIN_SUJETO = {"post", "page"}


@dataclass
class Pagina:
    clave: str                 # entity_type:slug
    tipo: str
    ruta: str
    sujeto: str
    title: str
    body_md: str
    h1: str
    target_keyword: str | None
    fila: object
    gsc: list[dict] = field(default_factory=list)

    @property
    def clics(self) -> int:
        return sum(int(q.get("clicks") or 0) for q in self.gsc)

    @property
    def impresiones(self) -> int:
        return sum(int(q.get("impressions") or 0) for q in self.gsc)


def _paginas(db, gsc: dict) -> list[Pagina]:
    out = []
    for sc in db.query(SeoContent).filter(SeoContent.published.is_(True)).all():
        modelo = _MODELOS.get(sc.entity_type)
        if modelo is None or not sc.meta_title:
            continue
        ent = db.get(modelo, sc.entity_id)
        if ent is None:
            continue
        sujeto, ruta = sujeto_y_ruta(ent, sc.entity_type)
        out.append(Pagina(f"{sc.entity_type}:{sc.slug}", sc.entity_type, ruta, sujeto,
                          sc.meta_title, sc.body_md or "", sc.h1 or "", sc.target_keyword,
                          sc, gsc.get(ruta) or []))
    for p in db.query(Post).filter(Post.status == "published").all():
        if not p.meta_title:
            continue
        ruta = f"/blog/{p.slug}"
        out.append(Pagina(f"post:{p.slug}", "post", ruta, "", p.meta_title, p.body_md or "",
                          p.title or "", p.target_keyword, p, gsc.get(ruta) or []))
    return out


NOMBRES: list[str] = []


def cargar_nombres(db) -> list[str]:
    """Títulos y nombres del catálogo: «Otra inútil canción para la paz» no es Title
    Case aunque el cuerpo de un post solo la escriba abriendo frase."""
    out = []
    for modelo in _MODELOS.values():
        for ent in db.query(modelo).all():
            for campo in ("title", "name", "stage_name", "full_name"):
                v = getattr(ent, campo, None)
                if v:
                    out.append(v)
    return out


def problemas(pg: Pagina) -> list[str]:
    v = seo_style.title_verdict(pg.title, body_md=pg.body_md, subject=pg.sujeto,
                                entity_type=pg.tipo, target_keyword=pg.target_keyword,
                                nombres=NOMBRES)
    return v.motivos


def _veredicto(pg: Pagina, nuevo: str, protegidas: list[dict], antes_cubre: set[str],
               alias: dict) -> tuple[list[str], set[str]]:
    v = seo_style.title_verdict(nuevo, body_md=pg.body_md, subject=pg.sujeto,
                                entity_type=pg.tipo, target_keyword=pg.target_keyword,
                                nombres=NOMBRES)
    motivos = list(v.motivos)
    # Cubrir el término principal NO bloquea (David: «si no se puede, no se
    # fuerza»). El 11-11-2026 exigirlo hizo escribir «de extremoduro a CIRA» sobre
    # alguien que nunca estuvo en Extremoduro. Lo que bloquea es perder una
    # consulta protegida, que mide lo que Google ya asocia de verdad.
    ahora = ranking_guard.cubiertas(nuevo, protegidas, alias)
    for q in sorted(antes_cubre - ahora):
        motivos.append(f"deja de cubrir la consulta protegida «{q}»")
    return motivos, ahora


def _prompt(pg: Pagina, protegidas_titulo: list[str], motivos_previos: list[str]) -> str:
    headings = [ln[3:].strip() for ln in pg.body_md.split("\n") if ln.startswith("## ")]
    kws = ", ".join(f"«{k}»" for k in seo_style.keywords_de(pg.target_keyword)) or "—"
    return (
        f"Reescribe el TITLE (etiqueta <title>) de esta página. Solo el title.\n"
        f"Tipo de página: {pg.tipo}. Sujeto: «{pg.sujeto or pg.h1}». H1: «{pg.h1}».\n"
        f"Title actual: «{pg.title}»\n"
        f"Lo que falla: {'; '.join(problemas(pg)) or 'nada grave'}\n"
        f"Término principal (cúbrelo sin pegarlo SI la página lo respalda; si el cuerpo "
        f"no habla de algo de él, NO lo metas): {kws}\n"
        + (f"Búsquedas reales que el title actual cubre y el nuevo TIENE que seguir "
           f"cubriendo (todas sus palabras): {', '.join(f'«{q}»' for q in protegidas_titulo)}\n"
           if protegidas_titulo else "")
        + f"Headings de la página: {' | '.join(headings[:12])}\n"
        f"Comienzo del cuerpo:\n{pg.body_md[:1500]}\n\n"
        f"{seo_style.PROMPT_META_RULES.split('DESCRIPTION')[0]}\n"
        f"{seo_style.EJEMPLOS_ORO.split('✗ «Barricada, grupo musical')[0]}\n"
        "Decide con la página delante: no hay plantilla. En una canción vale «Letra de X, "
        "de Extremoduro: …» o lo que mejor se lea; en un lugar, «La Plasencia de Robe…».\n"
        + (f"Tu intento anterior falló por: {'; '.join(motivos_previos)}\n" if motivos_previos
           else "")
        + 'Devuelve JSON {"titles": [tres alternativas distintas, de mejor a peor]}.'
    )


def proponer(client, pg: Pagina, alias: dict) -> dict:
    from scripts.seo.generate_deep import _chat

    protegidas = ranking_guard.consultas_protegidas(pg.gsc)
    antes_cubre = ranking_guard.cubiertas(pg.title, protegidas, alias)
    previos: list[str] = []
    descartes = []
    for _ in range(2):
        try:
            data = _chat(client, _prompt(pg, sorted(antes_cubre), previos),
                         max_tokens=400, temp=0.4)
        except Exception as exc:  # noqa: BLE001
            return {"elegido": None, "error": f"OpenAI: {exc}", "descartes": descartes}
        for t in data.get("titles") or []:
            t = seo_style.spanish_case(seo_style.quitar_comillas_envolventes(str(t)),
                                       f"{pg.body_md} {pg.sujeto} {pg.h1}")
            motivos, ahora = _veredicto(pg, t, protegidas, antes_cubre, alias)
            if not motivos:
                return {"elegido": t, "descartes": descartes, "protegidas": len(protegidas),
                        "cubre_antes": sorted(antes_cubre), "cubre_despues": sorted(ahora)}
            descartes.append({"title": t, "motivos": motivos})
            previos = motivos
    return {"elegido": None, "descartes": descartes, "protegidas": len(protegidas),
            "cubre_antes": sorted(antes_cubre)}


def _muestra(malas: list[Pagina], n: int) -> list[Pagina]:
    """Variada por tipo, con Plasencia siempre (es la que lo destapó)."""
    elegidas = [p for p in malas if p.clave == "place:plasencia"]
    tipos = ("song", "concept", "band", "person", "place", "album", "theme", "post", "artist")
    while len(elegidas) < n:
        antes = len(elegidas)
        for t in tipos:
            c = next((p for p in malas if p.tipo == t and p not in elegidas), None)
            if c and len(elegidas) < n:
                elegidas.append(c)
        if len(elegidas) == antes:
            break
    return elegidas


def problemas_h1(post, body_md: str) -> list[str]:
    return seo_style.h1_post_verdict(post.title or "", body_md=body_md, nombres=NOMBRES).motivos


def auditar(db, gsc: dict, todas: list[Pagina]) -> dict:
    """Todo lo que falla con las guardas v2: titles de todas las páginas y el
    título (H1) de los posts. Sin LLM: es la lista para revisar caso a caso."""
    filas = [{"pagina": p.clave, "campo": "meta_title", "ruta": p.ruta, "texto": p.title,
              "target_keyword": p.target_keyword, "clics": p.clics,
              "impresiones": p.impresiones, "problemas": problemas(p)}
             for p in todas if problemas(p)]
    for post in db.query(Post).filter(Post.status == "published").all():
        motivos = problemas_h1(post, post.body_md or "")
        if motivos:
            ruta = f"/blog/{post.slug}"
            g = gsc.get(ruta) or []
            filas.append({"pagina": f"post:{post.slug}", "campo": "h1", "ruta": ruta,
                          "texto": post.title, "target_keyword": post.target_keyword,
                          "clics": sum(int(q.get("clicks") or 0) for q in g),
                          "impresiones": sum(int(q.get("impressions") or 0) for q in g),
                          "problemas": motivos})
    return {"total_paginas": len(todas), "con_fallo": len(filas), "filas": filas}


def aplicar_aprobados(db, todas: list[Pagina], ruta_fichero: str, alias: dict,
                      apply: bool) -> list[str]:
    """Aplica el texto exacto aprobado, revalidado. Devuelve las rutas tocadas."""
    por_clave = {p.clave: p for p in todas}
    posts = {f"post:{p.slug}": p for p in db.query(Post).all()}
    rutas = []
    from pathlib import Path

    for linea in Path(ruta_fichero).read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        a = json.loads(linea)
        clave, campo, texto = a["pagina"], a.get("campo", "meta_title"), a["texto"].strip()
        if campo == "h1":
            post = posts.get(clave)
            if post is None:
                print(json.dumps({"pagina": clave, "error": "no es un post"}, ensure_ascii=False))
                continue
            motivos = seo_style.h1_post_verdict(texto, body_md=post.body_md or "",
                                                nombres=NOMBRES).motivos
            fila, antes, ruta = post, post.title, f"/blog/{post.slug}"
        else:
            pg = por_clave.get(clave)
            if pg is None:
                print(json.dumps({"pagina": clave, "error": "no está publicada"},
                                 ensure_ascii=False))
                continue
            protegidas = ranking_guard.consultas_protegidas(pg.gsc)
            antes_cubre = ranking_guard.cubiertas(pg.title, protegidas, alias)
            motivos, _ = _veredicto(pg, texto, protegidas, antes_cubre, alias)
            fila, antes, ruta = pg.fila, pg.title, pg.ruta
        aplicado = False
        if apply and not motivos and texto != antes:
            db.add(ContentRevision(
                target_kind="post" if clave.startswith("post:") else "seo_content",
                target_id=fila.id, path=ruta, body_md=fila.body_md or "",
                meta_title=fila.meta_title, meta_description=fila.meta_description,
                h1=getattr(fila, "h1", None) or getattr(fila, "title", None), reason=REASON_V2))
            if campo == "h1":
                fila.title = texto
            else:
                fila.meta_title = texto
            db.commit()
            rutas.append(ruta)
            aplicado = True
        print(json.dumps({"pagina": clave, "campo": campo, "antes": antes, "despues": texto,
                          "motivos": motivos, "aplicado": aplicado}, ensure_ascii=False),
              flush=True)
    return rutas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pages", help="entity_type:slug separados por comas (post:slug)")
    ap.add_argument("--auditar", action="store_true", help="v2: todo lo que falla, sin LLM")
    ap.add_argument("--aprobados", help="v2: JSONL con el texto exacto aprobado")
    ap.add_argument("--sample", type=int)
    ap.add_argument("--exposicion", action="store_true",
                    help="lista las páginas con fallo ordenadas por exposición en GSC")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    gsc, periodo = load_gsc_pages()
    with SessionLocal() as db:
        from app.services.seo_opportunities import nombre_alias_index

        alias = nombre_alias_index(db)
        NOMBRES[:] = cargar_nombres(db)
        todas = _paginas(db, gsc)
        if args.auditar:
            json.dump({"periodo_gsc": periodo, **auditar(db, gsc, todas)},
                      __import__("sys").stdout, ensure_ascii=False, indent=1)
            return
        if args.aprobados:
            rutas = aplicar_aprobados(db, todas, args.aprobados, alias, args.apply)
            if rutas:
                from app.services.publishing import revalidate_paths
                revalidate_paths(rutas + ["/blog"])
            return
        malas = [p for p in todas if problemas(p)]
        if args.exposicion:
            malas.sort(key=lambda p: (p.clics, p.impresiones))
            json.dump({"periodo_gsc": periodo, "total": len(todas), "con_fallo": len(malas),
                       "paginas": [{"pagina": p.clave, "ruta": p.ruta, "title": p.title,
                                    "clics": p.clics, "impresiones": p.impresiones,
                                    "problemas": problemas(p)} for p in malas]},
                      __import__("sys").stdout, ensure_ascii=False, indent=1)
            return
        if args.pages:
            quiero = {x.strip() for x in args.pages.split(",")}
            objetivo = [p for p in todas if p.clave in quiero]
        elif args.sample:
            objetivo = _muestra(malas, args.sample)
        else:
            raise SystemExit("di --pages, --sample o --exposicion")

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        rutas = []
        for pg in objetivo:
            prop = proponer(client, pg, alias)
            aplicado = False
            if args.apply and prop.get("elegido"):
                f = pg.fila
                db.add(ContentRevision(
                    target_kind="post" if pg.tipo == "post" else "seo_content",
                    target_id=f.id, path=pg.ruta, body_md=f.body_md or "",
                    meta_title=f.meta_title, meta_description=f.meta_description,
                    h1=getattr(f, "h1", None) or getattr(f, "title", None), reason=REASON))
                f.meta_title = prop["elegido"]
                db.commit()
                rutas.append(pg.ruta)
                aplicado = True
            print(json.dumps({"pagina": pg.clave, "ruta": pg.ruta, "antes": pg.title,
                              "despues": prop.get("elegido"),
                              "target_keyword": pg.target_keyword,
                              "problemas_antes": problemas(pg),
                              "clics": pg.clics, "impresiones": pg.impresiones,
                              **{k: v for k, v in prop.items() if k != "elegido"},
                              "aplicado": aplicado}, ensure_ascii=False), flush=True)
    if rutas:
        from app.services.publishing import revalidate_paths
        revalidate_paths(rutas)


if __name__ == "__main__":
    main()
