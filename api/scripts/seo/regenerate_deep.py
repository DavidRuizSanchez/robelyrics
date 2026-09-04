"""Orquestador del BACKFILL deep-RAG: regenera en masa las páginas SEO con el
motor profundo (`generate_deep.generate_for_entity`).

Reanudable: con --only-shallow salta las entidades que YA tienen contenido
profundo (`sources_count IS NOT NULL`), así un re-run continúa donde lo dejó.
Construye el índice de corpus y las stats de enlazado UNA sola vez para todo el
lote (no por entidad).

El estado publicado lo gobierna SEO_KEEP_PUBLISHED (=1 → refresca en sitio sin
tumbar la página; recomendado para lo ya publicado).

Uso:
  # piloto: solo las personas que aún son superficiales, refresco en sitio
  SEO_KEEP_PUBLISHED=1 python -m scripts.seo.regenerate_deep --entity-type person --only-shallow
  # todo lo que falte, todos los tipos
  SEO_KEEP_PUBLISHED=1 python -m scripts.seo.regenerate_deep --only-shallow
  # un sondeo de 3 para probar
  SEO_KEEP_PUBLISHED=1 python -m scripts.seo.regenerate_deep --entity-type band --only-shallow --limit 3
"""
from __future__ import annotations

import argparse
import os

from openai import OpenAI
from sqlalchemy import select

from app.db.models import SeoContent
from app.db.session import SessionLocal
from app.services.entity_resolver import build_corpus_index, load_link_stats
from scripts.seo.common import log
from scripts.seo.generate_deep import _MODELS, generate_for_entity
from scripts.seo.keyword_planner import plan_for_worklist

# Entidades que NO entran al backfill: los artistas Robe/Extremoduro tienen su
# página flagship (deep a medida) y la persona robe-iniesta canibalizaría el
# hub /robe (KW "robe extremoduro" = 201k, asignada a /robe).
_EXCLUDE: set[tuple[str, str]] = {
    ("artist", "robe"),
    ("artist", "extremoduro"),
    ("person", "robe-iniesta"),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--entity-type", choices=list(_MODELS),
                    help="solo este tipo; omitir = todos los tipos")
    ap.add_argument("--only-shallow", action="store_true",
                    help="salta las entidades con deep-RAG ya hecho (sources_count NOT NULL)")
    ap.add_argument("--skip-kw-done", action="store_true",
                    help="salta las que YA tienen KW asignada (target_keyword NOT NULL); "
                         "resume del backfill KW-aware y protege fichas curadas a mano")
    ap.add_argument("--limit", type=int, default=None,
                    help="tope de entidades a procesar (para sondeos)")
    ap.add_argument("--slugs", default=None,
                    help="solo estos slugs (separados por coma); para muestras dirigidas. "
                         "OJO: un slug de canción se repite entre discos, así que esto "
                         "puede coger más de una entidad — usa --ids si quieres una sola")
    ap.add_argument("--ids", default=None,
                    help="solo estas entidades por id (separadas por coma). Es lo que usa "
                         "`gsc_optimize --apply`: con --slugs, las keywords de UNA página "
                         "se aplicaban a todas sus homónimas")
    ap.add_argument("--publish", action="store_true",
                    help="fuerza published=True (normalmente basta SEO_KEEP_PUBLISHED=1)")
    ap.add_argument("--no-keywords", action="store_true",
                    help="no planifica KW por entidad (solo nombre líder del meta)")
    ap.add_argument("--plan-only", action="store_true",
                    help="solo imprime el mapa de KW (primaria/secundarias/volumen) y sale, sin gastar LLM")
    args = ap.parse_args()

    types = [args.entity_type] if args.entity_type else list(_MODELS)
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    with SessionLocal() as db:
        log("construyendo índice de corpus + stats de enlazado (una vez)…")
        corpus_index = build_corpus_index(db)
        link_stats = load_link_stats()

        # Conjuntos de "ya hecho" para los filtros de resume.
        deep_done: set[tuple[str, int]] = set()
        kw_done: set[tuple[str, int]] = set()
        if args.only_shallow:
            for et, eid in db.execute(
                select(SeoContent.entity_type, SeoContent.entity_id)
                .where(SeoContent.sources_count.isnot(None))
            ).all():
                deep_done.add((et, eid))
        if args.skip_kw_done:
            for et, eid in db.execute(
                select(SeoContent.entity_type, SeoContent.entity_id)
                .where(SeoContent.target_keyword.isnot(None))
            ).all():
                kw_done.add((et, eid))

        only_slugs = {s.strip() for s in args.slugs.split(",")} if args.slugs else None
        only_ids = (
            {int(i) for i in args.ids.split(",") if i.strip().isdigit()}
            if args.ids else None
        )
        targets: list[tuple[str, object]] = []
        for et in types:
            model = _MODELS[et]
            for ent in db.execute(select(model).order_by(model.slug)).scalars().all():
                if (et, ent.slug) in _EXCLUDE:
                    continue
                if only_ids is not None and ent.id not in only_ids:
                    continue
                if only_slugs and ent.slug not in only_slugs:
                    continue
                if args.only_shallow and (et, ent.id) in deep_done:
                    continue
                if args.skip_kw_done and (et, ent.id) in kw_done:
                    continue
                targets.append((et, ent))

        if args.limit:
            targets = targets[: args.limit]

        total = len(targets)

        # Mapa de KW por entidad (DataForSEO en lote). Anti-canibalización: la
        # primaria siempre lleva el nombre de la entidad.
        kw_map: dict[int, tuple[str, list[str], int]] = {}
        if not args.no_keywords and targets:
            log("planificando keywords (DataForSEO, en lote)…")
            kw_map = plan_for_worklist(db, targets)
            log("MAPA DE KEYWORDS:")
            for et, ent in targets:
                prim, sec, vol = kw_map.get(id(ent), ("", [], 0))
                log(f"  {et}/{ent.slug}: «{prim}» (vol {vol})"
                    + (f" · sec: {', '.join(sec)}" if sec else ""))

        if args.plan_only:
            log("--plan-only: no se genera contenido. Revisa el mapa de KW arriba.", "ok")
            return

        keep = os.environ.get("SEO_KEEP_PUBLISHED") == "1"
        log(f"BACKFILL deep-RAG: {total} entidades [{', '.join(types)}] "
            f"· {'refresco en sitio' if keep else 'a BORRADOR'}"
            f"{' · only-shallow' if args.only_shallow else ''}"
            f"{'' if args.no_keywords else ' · KW-aware'}")

        ok = fail = 0
        for i, (et, ent) in enumerate(targets, 1):
            prim, sec, _ = kw_map.get(id(ent), (None, [], 0))
            log(f"[{i}/{total}] {et}/{ent.slug}" + (f"  →  «{prim}»" if prim else ""))
            try:
                done = generate_for_entity(
                    db, client, et, ent,
                    target_keyword=prim, secondary=sec,
                    publish=args.publish,
                    corpus_index=corpus_index, link_stats=link_stats,
                )
                ok += int(done)
                fail += int(not done)
            except Exception as ex:  # noqa: BLE001 — un fallo no debe parar el lote
                db.rollback()
                fail += 1
                log(f"  ERROR en {et}/{ent.slug}: {ex!r}", "err")

        log(f"FIN BACKFILL: {ok} OK · {fail} fallos · de {total}", "ok")


if __name__ == "__main__":
    main()
