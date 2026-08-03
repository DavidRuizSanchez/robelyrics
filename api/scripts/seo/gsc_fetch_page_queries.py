"""Fetch de queries por URL de entreinteriores.com desde GSC (F2.5, paso 2).

Vuelca a `data/gsc_page_queries.json` las consultas (impresiones/clics/posición) que
recibe cada página en las últimas ~12 semanas. Es la ENTRADA del job de
auto-optimización (`gsc_optimize.py`). Solo datos GSC reales; nada inventado.

Uso:
  python -m scripts.seo.gsc_fetch_page_queries
  python -m scripts.seo.gsc_fetch_page_queries --weeks 12 --out /app/data/gsc_page_queries.json
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, timedelta
from pathlib import Path

from app.services import gsc_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_LAG_DAYS = 3  # GSC no tiene los últimos ~3 días
_SITE_PREFIX = "https://entreinteriores.com"


def _path_of(url: str) -> str:
    if url.startswith(_SITE_PREFIX):
        return url[len(_SITE_PREFIX):] or "/"
    return url


def build_page_queries(weeks: int) -> dict:
    if not gsc_client.is_configured():
        logger.warning("GSC no configurado (falta token); no se genera nada.")
        return {}
    end = date.today() - timedelta(days=_LAG_DAYS)
    start = end - timedelta(days=weeks * 7)
    rows = gsc_client.page_query_rows(start.isoformat(), end.isoformat())
    logger.info("filas page+query: %d (%s → %s)", len(rows), start, end)
    pages: dict[str, list[dict]] = {}
    for r in rows:
        page, query = r["keys"]
        pages.setdefault(_path_of(page), []).append({
            "query": query,
            "impressions": int(r.get("impressions", 0)),
            "clicks": int(r.get("clicks", 0)),
            "position": round(float(r.get("position", 0)), 1),
            "ctr": round(float(r.get("ctr", 0)), 4),
        })
    for qs in pages.values():
        qs.sort(key=lambda x: -x["impressions"])
    return {
        "site": gsc_client.SITE_URL,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "pages": pages,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch de queries por URL desde GSC.")
    ap.add_argument("--weeks", type=int, default=12)
    ap.add_argument("--out", default=None, help="ruta de salida (default data/gsc_page_queries.json)")
    ap.add_argument("--permitir-vacio", action="store_true",
                    help="escribir aunque GSC no devuelva ninguna página (solo para un sitio "
                         "recién dado de alta, que todavía no tiene datos)")
    args = ap.parse_args()

    data = build_page_queries(args.weeks)
    if not data:
        return
    # Un volcado sin páginas NO se escribe: cuando el token caduca, GSC devuelve
    # cero filas y este job sobreescribía el JSON bueno con `"pages": {}` — y el
    # rsync se lo llevaba a prod. El fichero anterior es dato real y viejo; el
    # vacío no es dato ninguno. Salir con error corta la cadena del .sh.
    if not data.get("pages") and not args.permitir_vacio:
        logger.error(
            "GSC no ha devuelto NINGUNA página. No se escribe nada para no machacar "
            "el último volcado bueno. Causa habitual: el refresh_token caducó o fue "
            "revocado (mira si arriba hay un WARNING '[gsc] no se pudo refrescar el "
            "token'). Re-autoriza con: python -m scripts.seo.gsc_reauth"
        )
        raise SystemExit(1)
    data_dir = Path(args.out).parent if args.out else (
        Path(__file__).resolve().parents[2] / "data"
    )
    data_dir.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else (data_dir / "gsc_page_queries.json")
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    logger.info("escrito %s (%d páginas)", out, len(data.get("pages", {})))

    # También el formato PLANO que ya lee keyword_research._gsc_queries
    # (data/gsc_queries.json): así regenerate_deep aprovecha la señal GSC real.
    # Se agrega por query (mejor posición, máx impresiones/clics).
    flat: dict[str, dict] = {}
    for qs in data["pages"].values():
        for q in qs:
            f = flat.get(q["query"])
            if not f:
                flat[q["query"]] = {"query": q["query"], "clicks": q["clicks"],
                                    "impressions": q["impressions"], "position": q["position"]}
            else:
                f["impressions"] += q["impressions"]
                f["clicks"] += q["clicks"]
                f["position"] = min(f["position"], q["position"])
    flat_path = data_dir / "gsc_queries.json"
    flat_path.write_text(
        json.dumps(sorted(flat.values(), key=lambda x: -x["impressions"]), ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    logger.info("escrito %s (%d queries)", flat_path, len(flat))


if __name__ == "__main__":
    main()
