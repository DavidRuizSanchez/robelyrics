"""Ola de keyword research: cierre transitivo por asset.

    python -m scripts.seo.kw_run --run 2026-08-01a --assets album --dry-run
    python -m scripts.seo.kw_run --run 2026-08-01a --assets album --max-spend 40

`--dry-run` no llama a ninguna API: enumera los assets y sus semillas y proyecta
el coste con los precios reales de la cuenta. Sirve para ver el tamaño de la ola
ANTES de gastar.

El run es reanudable: la caché de respuestas crudas es compartida entre runs, así
que si el gate corta (tope de gasto o límite diario de la cuenta) basta con
relanzar y solo se pagan las llamadas que faltaban.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Album, Artist, Song
from app.db.session import SessionLocal
from app.services.kw_cache import (
    AHREFS_UNITS_PER_ROW,
    BudgetExceeded,
    CacheStore,
    RunPaths,
    SpendLedger,
    forecast_cost,
    utcnow,
)
from app.services.kw_normalize import build_vocab, strip_title_suffix
from app.services.kw_universe import (
    Asset,
    build_seeds,
    close_universe,
    enrich_missing,
    row_to_dict,
)

# `./data` se monta READ-ONLY encima de /app/data (docker-compose.yml:98), así que
# la salida no puede vivir ahí. /app es `./api`, montado rw → api/kw_out/ en el host.
OUT_ROOT = Path("/app/kw_out")

CSV_FIELDS = [
    "asset_type", "asset_slug", "asset_title", "asset_url", "keyword",
    "keyword_norm", "variant_group", "volume", "volume_source",
    "volume_fetched_at", "difficulty", "cpc", "competition", "intent_api",
    "intent_lex", "n_words", "is_brand", "belongs_reason", "belongs_kind",
    "off_topic", "discovered_round", "discovered_from", "providers", "endpoints",
    "evidence_ref",
]


def enumerate_assets(db: Session, kinds: set[str], only: list[str] | None) -> list[Asset]:
    assets: list[Asset] = []

    if "artist" in kinds:
        for artist in db.execute(select(Artist)).scalars():
            assets.append(Asset(
                asset_type="artist", slug=artist.slug, title=artist.name,
                artist_slug=artist.slug, artist_name=artist.name,
                url_path=f"/{artist.slug}",
            ))

    if "album" in kinds:
        rows = db.execute(select(Album, Artist).join(Artist, Album.artist_id == Artist.id)).all()
        for album, artist in rows:
            titles = db.execute(
                select(Song.title).where(Song.album_id == album.id).order_by(Song.track_number)
            ).scalars().all()
            # Sin quitar el sufijo desambiguador, «Jesucristo García (Rock
            # Transgresivo)» entra de semilla y no devuelve nada.
            limpios = []
            for t in titles:
                base = strip_title_suffix(t or "")
                if base and base not in limpios:
                    limpios.append(base)
            assets.append(Asset(
                asset_type="album", slug=album.slug, title=album.title,
                artist_slug=artist.slug, artist_name=artist.name,
                url_path=f"/{artist.slug}/{album.slug}",
                extra_seeds=tuple(limpios[:10]),
            ))

    if "song" in kinds:
        rows = db.execute(
            select(Song, Album, Artist)
            .join(Album, Song.album_id == Album.id)
            .join(Artist, Album.artist_id == Artist.id)
        ).all()
        for song, album, artist in rows:
            assets.append(Asset(
                asset_type="song", slug=song.slug,
                title=strip_title_suffix(song.title or ""),
                artist_slug=artist.slug, artist_name=artist.name,
                url_path=f"/{artist.slug}/{album.slug}/{song.slug}",
            ))

    if only:
        wanted = set(only)
        assets = [a for a in assets if a.slug in wanted]
    return assets


def do_dry_run(assets: list[Asset]) -> None:
    """Proyección con los precios reales. Media medida: ~42 kws/semilla en ronda 1."""
    print(f"\n{'ASSET':<46} {'SEMILLAS':>9} {'LLAMADAS~':>10} {'COSTE~':>9}")
    print("-" * 78)
    total_calls = total_cost = 0.0
    for a in assets:
        seeds = build_seeds(a)
        # 2 endpoints por semilla en ronda 1; las rondas siguientes expanden sobre
        # lo descubierto. Factor 3,5 derivado del ratio medido nuevas/semilla.
        calls = len(seeds) * 2 * 3.5
        cost = forecast_cost("labs", 45, int(calls))
        total_calls += calls
        total_cost += cost
        print(f"{a.ref:<46} {len(seeds):>9} {calls:>10.0f} {cost:>8.2f}$")
    print("-" * 78)
    print(f"{'TOTAL':<46} {'':>9} {total_calls:>10.0f} {total_cost:>8.2f}$")
    print(f"\nAhrefs (a {AHREFS_UNITS_PER_ROW['minimal']} u/fila, select mínimo): "
          f"~{int(total_calls * 45 * AHREFS_UNITS_PER_ROW['minimal']):,} unidades si se "
          "replicara todo — se decide tras ver el universo real de DataForSEO.")
    print(f"\nLímite de la cuenta: 1.000 llamadas/día → ~{total_calls / 1000:.1f} día(s).")
    print("Proyección desde 4 llamadas reales del 2026-08-01. No es gasto observado.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True, help="id del run, p.ej. 2026-08-01a")
    ap.add_argument("--assets", default="album,artist",
                    help="tipos: album,artist,song (coma)")
    ap.add_argument("--only", action="append", help="limitar a estos slugs")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-spend", type=float, default=40.0)
    ap.add_argument("--max-ahrefs-units", type=int, default=350_000)
    ap.add_argument("--max-calls", type=int, default=1000)
    ap.add_argument("--max-rounds", type=int, default=6)
    ap.add_argument("--no-enrich", action="store_true")
    args = ap.parse_args()

    kinds = {k.strip() for k in args.assets.split(",") if k.strip()}
    db = SessionLocal()
    try:
        assets = enumerate_assets(db, kinds, args.only)
        if not assets:
            print("No hay assets que casen con el filtro.", file=sys.stderr)
            return 1
        if args.dry_run:
            do_dry_run(assets)
            return 0
        vocab = build_vocab(db)
    finally:
        db.close()

    print(f"Vocabulario del universo: {len(vocab.strong_titles)} títulos inequívocos, "
          f"{len(vocab.weak_titles)} ambiguos, {len(vocab.people)} personas.")

    paths = RunPaths(root=OUT_ROOT, run_id=args.run)
    cache = CacheStore(paths)
    ledger = SpendLedger(
        paths=paths, max_spend_usd=args.max_spend,
        max_ahrefs_units=args.max_ahrefs_units, max_calls_per_day=args.max_calls,
    )

    by_asset_dir = paths.run_dir / "by-asset"
    by_asset_dir.mkdir(parents=True, exist_ok=True)
    master_path = paths.run_dir / "master.csv"
    revisar_path = paths.run_dir / "revisar_homonimos.csv"
    offtopic_path = paths.run_dir / "offtopic.csv"
    trace: list[dict] = []

    def progress(asset: Asset, r: dict) -> None:
        print(f"  [{asset.ref}] ronda {r['round']}: {r['seeds_consultadas']} semillas "
              f"→ {r['nuevas_fuertes']} inequívocas + {r['nuevas_ambiguas']} ambiguas "
              f"(universo {r['universo_acumulado']}, offtopic {r['offtopic_acumulado']})")

    # Tres cubos separados porque tienen calidades incompatibles y mezclarlos
    # arruinaría el entregable:
    #   master.csv             → keywords con marca. Certeza alta, accionable ya.
    #   revisar_homonimos.csv  → casan por título SIN marca. Aquí vive «el día de
    #                            la bestia» (la película de Álex de la Iglesia,
    #                            14.800 de volumen) junto a la canción. Necesita
    #                            ojo humano antes de usarse.
    #   offtopic.csv           → lo que no pertenece. Se guarda para poder
    #                            auditar la guarda, no se tira.
    master_fh = master_path.open("w", newline="", encoding="utf-8")
    rev_fh = revisar_path.open("w", newline="", encoding="utf-8")
    off_fh = offtopic_path.open("w", newline="", encoding="utf-8")
    master = csv.DictWriter(master_fh, fieldnames=CSV_FIELDS)
    revw = csv.DictWriter(rev_fh, fieldnames=CSV_FIELDS)
    offw = csv.DictWriter(off_fh, fieldnames=CSV_FIELDS)
    master.writeheader()
    revw.writeheader()
    offw.writeheader()

    stopped = None
    try:
        for idx, asset in enumerate(assets, 1):
            print(f"\n[{idx}/{len(assets)}] {asset.ref} — «{asset.title}»")
            try:
                universe, rounds = close_universe(
                    asset, vocab=vocab, cache=cache, ledger=ledger,
                    max_rounds=args.max_rounds, on_progress=progress,
                )
            except BudgetExceeded as exc:
                stopped = str(exc)
                break

            rows = list(universe.values())
            if not args.no_enrich:
                try:
                    enrich_missing(rows, cache=cache, ledger=ledger, asset=asset.ref)
                except BudgetExceeded as exc:
                    stopped = str(exc)

            by_vol = lambda r: (-(r.volume or 0), r.keyword)  # noqa: E731
            keep = sorted((r for r in rows if r.belongs_kind == "brand"), key=by_vol)
            revisar = sorted(
                (r for r in rows if r.belongs_kind in ("title_strong", "title_weak")),
                key=by_vol,
            )
            drop = [r for r in rows if r.off_topic]

            with (by_asset_dir / f"{asset.asset_type}__{asset.slug}.csv").open(
                "w", newline="", encoding="utf-8"
            ) as fh:
                w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
                w.writeheader()
                for r in keep:
                    w.writerow(row_to_dict(r, asset))

            for r in keep:
                master.writerow(row_to_dict(r, asset))
            for r in revisar:
                revw.writerow(row_to_dict(r, asset))
            for r in drop:
                offw.writerow(row_to_dict(r, asset))
            for fh_ in (master_fh, rev_fh, off_fh):
                fh_.flush()

            con_vol = sum(1 for r in keep if (r.volume or 0) > 0)
            print(f"  → núcleo {len(keep)} kws ({con_vol} con volumen medido), "
                  f"{len(revisar)} por revisar, {len(drop)} off-topic. "
                  f"Gasto acumulado ${ledger.spent_usd:.4f} en {ledger.calls} llamadas.")
            trace.append({
                "asset": asset.ref, "title": asset.title, "url": asset.url_path,
                "rondas": rounds, "nucleo": len(keep), "con_volumen": con_vol,
                "revisar": len(revisar), "offtopic": len(drop),
            })
            if stopped:
                break
    finally:
        master_fh.close()
        rev_fh.close()
        off_fh.close()

    summary = ledger.summary()
    manifest = {
        "run_id": args.run,
        "generado": utcnow(),
        "assets_pedidos": len(assets),
        "assets_completados": len(trace),
        "parado_por": stopped,
        "gasto": summary,
        "assets": trace,
    }
    (paths.run_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n" + "=" * 78)
    print(f"Assets completados: {len(trace)}/{len(assets)}")
    print(f"Coste REAL: ${summary['total_cost_usd']:.4f} en {summary['paid_calls']} "
          f"llamadas pagadas ({summary['cached_hits']} servidas de caché)")
    if stopped:
        print(f"PARADO: {stopped}")
        print("Relanzar el mismo comando reanuda sin repagar lo ya hecho.")
    print(f"Salida: {paths.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
