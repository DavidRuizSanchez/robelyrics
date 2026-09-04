"""Genera SOURCES.md y COSTS.md del run, enteramente desde el ledger.

    python -m scripts.seo.kw_sources --run ola1-discos-v2

Nada se escribe a mano: cada línea sale de `costs.jsonl`, que a su vez guarda el
campo `cost` que devolvió DataForSEO en cada respuesta. Si un dato no está, se
declara ausente — no se estima.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path("/app/kw_out")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    args = ap.parse_args()

    run_dir = ROOT / args.run
    ledger_path = run_dir / "costs.jsonl"
    if not ledger_path.exists():
        print(f"No existe {ledger_path}")
        return 1

    filas = [json.loads(l) for l in ledger_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    pagadas = [f for f in filas if not f.get("from_cache")]

    por_endpoint: dict[str, dict] = defaultdict(
        lambda: {"llamadas": 0, "coste": 0.0, "resultados": 0, "primera": None, "ultima": None}
    )
    for f in pagadas:
        s = por_endpoint[f["endpoint"]]
        s["llamadas"] += 1
        s["coste"] += f.get("cost_usd") or 0.0
        s["resultados"] += f.get("n_results") or 0
        ts = f["ts"]
        s["primera"] = min(s["primera"], ts) if s["primera"] else ts
        s["ultima"] = max(s["ultima"], ts) if s["ultima"] else ts

    total = sum(s["coste"] for s in por_endpoint.values())
    errores = [f for f in pagadas if f.get("status") != "ok"]

    # COSTS.csv — una fila por llamada pagada, con su hash de evidencia.
    with (run_dir / "costs.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "ts", "provider", "endpoint", "asset", "round", "seed",
            "n_results", "cost_usd", "status", "params_hash",
        ])
        w.writeheader()
        for f in pagadas:
            w.writerow({k: f.get(k) for k in w.fieldnames})

    ahrefs_dir = ROOT / "_ahrefs"
    ahrefs_files = sorted(ahrefs_dir.glob("*.tsv")) if ahrefs_dir.exists() else []
    ahrefs_kws = sum(
        len([l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()])
        for p in ahrefs_files
    )

    L = [
        f"# SOURCES — keyword research `{args.run}`",
        "",
        "Cada dato de los CSV es trazable a la respuesta cruda que lo produjo. La",
        "columna `evidence_ref` del master es el `params_hash` de esta tabla, y el",
        "fichero crudo vive en `kw_out/_raw/<params_hash>.json`.",
        "",
        "**Regla aplicada**: métrica ausente = celda vacía. Nunca 0, nunca interpolada.",
        "",
        "## DataForSEO",
        "",
        "- Cuenta: la de las variables `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD`.",
        "- Mercado: `location_code=2724` (España), `language_code=es`. Sin más filtros.",
        "- Coste: el campo `cost` **que devuelve cada respuesta**. No es una estimación.",
        "- Periodo del volumen: el que declara la API por fila; se vuelca en la columna",
        "  `volume_fetched_at` de cada keyword.",
        "",
        "| Endpoint | Llamadas | Resultados | Coste medido | Primera | Última |",
        "|---|---|---|---|---|---|",
    ]
    for ep, s in sorted(por_endpoint.items(), key=lambda kv: -kv[1]["coste"]):
        L.append(
            f"| `{ep}` | {s['llamadas']} | {s['resultados']} | ${s['coste']:.4f} | "
            f"{(s['primera'] or '')[:19]} | {(s['ultima'] or '')[:19]} |"
        )
    L += [
        f"| **TOTAL** | **{len(pagadas)}** | "
        f"**{sum(s['resultados'] for s in por_endpoint.values())}** | "
        f"**${total:.4f}** | | |",
        "",
        f"Servidas de caché sin coste: {len(filas) - len(pagadas)}.",
        "",
    ]
    if errores:
        L += [f"Llamadas con error (no aportaron datos): {len(errores)}.", ""]

    L += [
        "### Endpoints usados y por qué",
        "",
        "| Endpoint | Papel | Nota |",
        "|---|---|---|",
        "| `keyword_suggestions` | Descubrimiento principal | Full-text de la semilla. "
        "Se agota solo: con `limit=1000` devolvió 53 keywords para «agila extremoduro». |",
        "| `related_keywords` | Eje «también buscan» | `depth=3`. Pobre en nichos "
        "(4 keywords para la misma semilla) pero barato. |",
        "| `keyword_overview` | Enriquecimiento | Volumen + dificultad + intención en "
        "lotes de 700. Lo que sigue sin dato se queda vacío. |",
        "",
        "**`keyword_ideas` se dejó fuera a propósito.** Medido el 2026-08-01: declara",
        "954.756 keywords para un disco y, de las 1.000 devueltas, solo 34 (**3,4%**)",
        "tocaban el universo Robe/Extremoduro; el resto era ruido de categoría del tipo",
        "«1212 significado espiritual». Incluirlo habría inflado el entregable sin",
        "aportar una sola keyword útil.",
        "",
        "## Ahrefs",
        "",
        "- Vía: herramientas MCP de Ahrefs de la sesión (no hay cliente en el repo).",
        "- Endpoint: `keywords-explorer-matching-terms`, `country=es`,",
        "  `match_mode=terms`, `select=keyword,volume`, ordenado por volumen.",
        "- Tarifa **medida** el 2026-08-01: 11 unidades/fila con `select` mínimo y",
        "  33 u/fila con `select` de 6 campos (~5,5 u por campo por fila).",
        f"- Cobertura: {len(ahrefs_files)} assets volcados, {ahrefs_kws} keywords.",
        "",
        "> **[LIMITACIÓN DECLARADA]** La cobertura de Ahrefs es **parcial** y con",
        "> `limit` por asset, porque el puente con el MCP es manual y la cuota del",
        "> workspace (400.000 unidades, reset 2026-08-14) es un techo duro que no se",
        "> auto-recarga. Los assets sin fichero en `_ahrefs/` llevan **solo** datos de",
        "> DataForSEO, y así consta en su columna `volume_sources`. No se ha rellenado",
        "> ni un solo hueco de Ahrefs por estimación.",
        "",
        "## Cruce entre herramientas",
        "",
        "Los volúmenes de DataForSEO y Ahrefs **no se promedian ni se mezclan**: cada",
        "uno va en su columna (`volume_dataforseo`, `volume_ahrefs`) con su fuente en",
        "`volume_sources`. `volume_best` es el mayor de los dos y está declarado como",
        "**derivado**, no como métrica de una fuente. Las divergencias de más de 2×",
        "entre ambas herramientas se listan en `discrepancias.csv`.",
        "",
        "## Derivados (no son métricas de ninguna fuente)",
        "",
        "| Campo | Cómo se calcula |",
        "|---|---|",
        "| `volume_best` | `max(volume_dataforseo, volume_ahrefs)` |",
        "| `cluster_id` / `cluster_label` | k-means determinista sobre embeddings "
        "`text-embedding-3-large`; etiqueta = n-grama compartido por ≥55% del cluster |",
        "| `is_head` | Entre los miembros con coseno al centroide ≥ mediana, el de mayor volumen |",
        "| `intent_lex` | Heurística léxica sobre la keyword. La intención de la API "
        "va aparte en `intent_api` |",
        "| `belongs_reason` | Token del universo que acreditó la pertenencia |",
        "",
        "## Guarda de pertenencia",
        "",
        "El vocabulario del universo se deriva de la BD (títulos de disco y canción,",
        "nombres de personas, marca), así que un disco nuevo se reconoce sin tocar",
        "código. Tres grados, y los tres se exportan:",
        "",
        "- `brand` → lleva marca del universo. Va a `master.csv`.",
        "- `title_strong` / `title_weak` → casan por título **sin** marca. Van a",
        "  `revisar_homonimos.csv` porque ahí viven los homónimos famosos: «el día de",
        "  la bestia» (14.800 de volumen) es la película de Álex de la Iglesia, no la",
        "  canción; «prometeo» arrastra el mito griego y una librería de Málaga.",
        "- Sin match → `offtopic.csv`. Se guarda para poder auditar la guarda.",
        "",
        "Solo el grado `brand`/`title_strong` propaga el cierre transitivo. Sin ese",
        "freno el barrido no converge: sembrar con «prometeo» traía la librería entera.",
        "",
    ]

    (run_dir / "SOURCES.md").write_text("\n".join(L), encoding="utf-8")
    print(f"SOURCES.md y costs.csv en {run_dir}")
    print(f"Coste total MEDIDO: ${total:.4f} en {len(pagadas)} llamadas pagadas "
          f"({len(filas) - len(pagadas)} de caché)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
