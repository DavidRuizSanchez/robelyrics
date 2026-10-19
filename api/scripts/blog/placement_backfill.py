"""Analiza si cada propuesta del blog es contenido nuevo o amplía una página.

Lo hace solo `generate_proposals` para las que entran cada lunes; esto es para
las que ya estaban en el banco y para recalcular cuando llega un volcado nuevo de
GSC.

Uso:
    python -m scripts.blog.placement_backfill --dry-run          (solo enseña)
    python -m scripts.blog.placement_backfill                    (guarda las que faltan)
    python -m scripts.blog.placement_backfill --all --ids 484,485 (recalcula esas)
"""
from __future__ import annotations

import argparse
import logging

from openai import OpenAI

from app.config import get_settings
from app.db.session import SessionLocal
from app.services import content_placement

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--all", action="store_true",
                        help="recalcular también las que ya tienen análisis")
    parser.add_argument("--ids", default="", help="ids separados por comas")
    parser.add_argument("--no-serp", action="store_true")
    parser.add_argument("--no-semantic", action="store_true")
    args = parser.parse_args()

    ids = [int(x) for x in args.ids.split(",") if x.strip().isdigit()] or None
    key = get_settings().openai_api_key
    client = OpenAI(api_key=key) if key else None
    with SessionLocal() as db:
        res = content_placement.analyze_pending(
            db, ids=ids, only_missing=not args.all, dry_run=args.dry_run, client=client,
            use_serp=not args.no_serp, use_semantic=not args.no_semantic)
        for prop, pl in res:
            print(f"#{prop.id} «{prop.title}» [{prop.target_keyword}]")
            print(f"   → {pl.decision.upper()} ({pl.confidence}) · "
                  f"{content_placement.headline(pl.to_dict())}")
            for r in pl.reasons:
                print(f"     · {r}")
            for c in pl.candidates:
                print(f"     - {c.path} [{c.kind}] impr={c.gsc_impressions} "
                      f"pos={c.gsc_position} serp={c.serp_rank} sim={c.similarity} "
                      f"ancla={c.is_anchor} score={c.score()}")
        print(f"{len(res)} propuestas analizadas"
              + (" (dry-run: nada guardado)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
