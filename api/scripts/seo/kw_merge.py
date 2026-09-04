"""Fusiona DataForSEO + Ahrefs, deduplica, agrupa por semántica y monta el entregable.

    python -m scripts.seo.kw_merge --run ola1-discos

Entradas:
  kw_out/<run>/master.csv          keywords de DataForSEO (núcleo, con marca)
  kw_out/_ahrefs/<tipo>__<slug>.tsv   keyword<TAB>volumen, volcados de Ahrefs MCP

Salidas en kw_out/<run>/entregable/:
  master.csv          universo completo con cluster asignado
  clusters.csv        un registro por cluster
  discrepancias.csv   keywords donde DataForSEO y Ahrefs difieren >2x
  by-asset/*.csv
  SOURCES.md

Reglas que no se negocian:
  - Los volúmenes de las dos herramientas NO se promedian ni se elige uno en
    silencio. Se guardan ambos con su fuente y las divergencias se reportan.
  - Sin dato es NULL (celda vacía), nunca 0.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from app.services.embeddings import EMBED_MODEL, get_embedder
from app.services.kw_clustering import cluster_keywords
from app.services.kw_normalize import kw_norm

ROOT = Path("/app/kw_out")
AHREFS_DIR = ROOT / "_ahrefs"

OUT_FIELDS = [
    "asset_type", "asset_slug", "asset_title", "asset_url",
    "cluster_id", "cluster_label", "is_head",
    "keyword", "variant_group",
    "volume_dataforseo", "volume_ahrefs", "volume_best", "volume_sources",
    "difficulty", "cpc", "competition", "intent_api", "intent_lex",
    "n_words", "belongs_reason", "discovered_round", "discovered_from",
    "providers", "endpoints", "evidence_ref",
]


def load_ahrefs() -> dict[str, dict[str, int]]:
    """{asset_key: {keyword_norm: volumen}} desde los TSV volcados del MCP."""
    out: dict[str, dict[str, int]] = {}
    if not AHREFS_DIR.exists():
        return out
    for path in sorted(AHREFS_DIR.glob("*.tsv")):
        key = path.stem  # p.ej. album__la-ley-innata
        rows: dict[str, int] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            kw, vol = parts[0].strip(), parts[1].strip()
            try:
                rows[kw_norm(kw)] = int(vol)
            except ValueError:
                continue
        out[key] = rows
    return out


def to_int(v: str) -> int | None:
    v = (v or "").strip()
    if not v:
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("--target-per-cluster", type=int, default=12)
    ap.add_argument("--max-k", type=int, default=40)
    ap.add_argument("--no-embed", action="store_true",
                    help="salta el clustering (para probar el resto del pipeline)")
    args = ap.parse_args()

    run_dir = ROOT / args.run
    master_in = run_dir / "master.csv"
    if not master_in.exists():
        print(f"No existe {master_in}")
        return 1

    ahrefs = load_ahrefs()
    print(f"Ahrefs: {len(ahrefs)} assets volcados, "
          f"{sum(len(v) for v in ahrefs.values())} keywords.")

    por_asset: dict[tuple[str, str], list[dict]] = defaultdict(list)
    meta: dict[tuple[str, str], dict] = {}
    for row in csv.DictReader(master_in.open(encoding="utf-8")):
        key = (row["asset_type"], row["asset_slug"])
        por_asset[key].append(row)
        meta.setdefault(key, {"title": row["asset_title"], "url": row["asset_url"]})

    print(f"DataForSEO: {len(por_asset)} assets, "
          f"{sum(len(v) for v in por_asset.values())} keywords.")

    out_dir = run_dir / "entregable"
    (out_dir / "by-asset").mkdir(parents=True, exist_ok=True)

    embedder = None if args.no_embed else get_embedder()

    master_fh = (out_dir / "master.csv").open("w", newline="", encoding="utf-8")
    clus_fh = (out_dir / "clusters.csv").open("w", newline="", encoding="utf-8")
    disc_fh = (out_dir / "discrepancias.csv").open("w", newline="", encoding="utf-8")
    mw = csv.DictWriter(master_fh, fieldnames=OUT_FIELDS)
    cw = csv.DictWriter(clus_fh, fieldnames=[
        "asset_type", "asset_slug", "cluster_id", "cluster_label", "head_keyword",
        "size", "total_volume", "label_source",
    ])
    dw = csv.DictWriter(disc_fh, fieldnames=[
        "asset_slug", "keyword", "volume_dataforseo", "volume_ahrefs", "ratio",
    ])
    mw.writeheader()
    cw.writeheader()
    dw.writeheader()

    total_kw = total_clusters = total_disc = 0
    resumen: list[dict] = []

    for (atype, aslug), rows in sorted(por_asset.items()):
        ah = ahrefs.get(f"{atype}__{aslug}", {})
        info = meta[(atype, aslug)]

        fusion: dict[str, dict] = {}
        for r in rows:
            k = r["keyword_norm"] or kw_norm(r["keyword"])
            fusion[k] = {
                "keyword": r["keyword"], "variant_group": r["variant_group"],
                "vol_dfs": to_int(r["volume"]), "vol_ah": None,
                "difficulty": r["difficulty"], "cpc": r["cpc"],
                "competition": r["competition"], "intent_api": r["intent_api"],
                "intent_lex": r["intent_lex"], "n_words": r["n_words"],
                "belongs_reason": r["belongs_reason"],
                "discovered_round": r["discovered_round"],
                "discovered_from": r["discovered_from"],
                "providers": set((r["providers"] or "").split("|")) - {""},
                "endpoints": set((r["endpoints"] or "").split("|")) - {""},
                "evidence": set((r["evidence_ref"] or "").split("|")) - {""},
            }

        # Ahrefs aporta keywords que DataForSEO no tenía: entran como nuevas.
        for k, vol in ah.items():
            if k in fusion:
                fusion[k]["vol_ah"] = vol
                fusion[k]["providers"].add("ahrefs")
            else:
                fusion[k] = {
                    "keyword": k, "variant_group": "", "vol_dfs": None,
                    "vol_ah": vol, "difficulty": "", "cpc": "", "competition": "",
                    "intent_api": "", "intent_lex": "", "n_words": len(k.split()),
                    "belongs_reason": "ahrefs:solo", "discovered_round": "",
                    "discovered_from": "", "providers": {"ahrefs"},
                    "endpoints": {"matching-terms"}, "evidence": {"ahrefs_mcp"},
                }

        keys = sorted(fusion)
        keywords = [fusion[k]["keyword"] for k in keys]
        # Para pesar el clustering se usa el mayor de los dos volúmenes; eso NO
        # es «elegir fuente», solo priorizar el centro de masa del cluster.
        volumes = [
            max(fusion[k]["vol_dfs"] or 0, fusion[k]["vol_ah"] or 0) for k in keys
        ]

        clusters = []
        cluster_de: dict[int, int] = {}
        heads: set[int] = set()
        if embedder and len(keywords) >= 2:
            vecs: list[list[float]] = []
            for i in range(0, len(keywords), 256):
                vecs += embedder.embed(keywords[i : i + 256])
            clusters = cluster_keywords(
                keywords, volumes, vecs,
                target_per_cluster=args.target_per_cluster, max_k=args.max_k,
            )
            for cl in clusters:
                for i in cl.members:
                    cluster_de[i] = cl.id
                heads.add(keywords.index(cl.head))

        filas = []
        for i, k in enumerate(keys):
            f = fusion[k]
            vd, va = f["vol_dfs"], f["vol_ah"]
            fuentes = "|".join(
                s for s, v in (("dataforseo", vd), ("ahrefs", va)) if v is not None
            )
            cid = cluster_de.get(i, "")
            filas.append({
                "asset_type": atype, "asset_slug": aslug,
                "asset_title": info["title"], "asset_url": info["url"],
                "cluster_id": cid,
                "cluster_label": clusters[cid].label if clusters and cid != "" else "",
                "is_head": i in heads,
                "keyword": f["keyword"], "variant_group": f["variant_group"],
                "volume_dataforseo": vd if vd is not None else "",
                "volume_ahrefs": va if va is not None else "",
                "volume_best": max(vd or 0, va or 0) if (vd is not None or va is not None) else "",
                "volume_sources": fuentes,
                "difficulty": f["difficulty"], "cpc": f["cpc"],
                "competition": f["competition"], "intent_api": f["intent_api"],
                "intent_lex": f["intent_lex"], "n_words": f["n_words"],
                "belongs_reason": f["belongs_reason"],
                "discovered_round": f["discovered_round"],
                "discovered_from": f["discovered_from"],
                "providers": "|".join(sorted(f["providers"])),
                "endpoints": "|".join(sorted(f["endpoints"])),
                "evidence_ref": "|".join(sorted(f["evidence"])),
            })
            # Divergencia >2x entre herramientas: se reporta, no se resuelve sola.
            if vd and va and (max(vd, va) / max(1, min(vd, va))) > 2:
                dw.writerow({
                    "asset_slug": aslug, "keyword": f["keyword"],
                    "volume_dataforseo": vd, "volume_ahrefs": va,
                    "ratio": round(max(vd, va) / max(1, min(vd, va)), 2),
                })
                total_disc += 1

        filas.sort(key=lambda r: (-(r["volume_best"] or 0), r["keyword"]))
        with (out_dir / "by-asset" / f"{atype}__{aslug}.csv").open(
            "w", newline="", encoding="utf-8"
        ) as fh:
            w = csv.DictWriter(fh, fieldnames=OUT_FIELDS)
            w.writeheader()
            w.writerows(filas)
        mw.writerows(filas)

        for cl in clusters:
            cw.writerow({
                "asset_type": atype, "asset_slug": aslug, "cluster_id": cl.id,
                "cluster_label": cl.label, "head_keyword": cl.head,
                "size": cl.size, "total_volume": cl.total_volume,
                "label_source": "ngram",
            })

        total_kw += len(filas)
        total_clusters += len(clusters)
        solo_ah = sum(1 for f in filas if f["providers"] == "ahrefs")
        resumen.append({
            "asset": f"{atype}:{aslug}", "titulo": info["title"],
            "keywords": len(filas), "clusters": len(clusters),
            "solo_ahrefs": solo_ah,
            "volumen_total": sum(r["volume_best"] or 0 for r in filas),
        })
        print(f"  {atype}:{aslug:<42} {len(filas):>5} kws  {len(clusters):>3} clusters"
              f"  (+{solo_ah} solo de Ahrefs)")

    for fh in (master_fh, clus_fh, disc_fh):
        fh.close()

    (out_dir / "resumen.json").write_text(
        json.dumps({
            "run": args.run, "assets": len(por_asset), "keywords": total_kw,
            "clusters": total_clusters, "discrepancias": total_disc,
            "embed_model": EMBED_MODEL if embedder else None,
            "detalle": resumen,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nTOTAL: {total_kw} keywords, {total_clusters} clusters, "
          f"{total_disc} discrepancias entre herramientas.")
    print(f"Entregable: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
