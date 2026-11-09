"""Tráfico por origen en GA4: la vara de medir de las redes sociales.

Sesiones, sesiones con interacción y duración media por `sessionSource/sessionMedium`
y, con `--campanas`, por `sessionCampaignName` (el `utm_campaign` de cada enlace).

GA4 solo cuenta a quien ACEPTA las cookies (`ConsentManager.tsx`), así que se queda
por debajo del log de Caddy, que lo cuenta todo. El descuadre es esperable; lo que
vale es comparar GA4 consigo mismo antes y después.

Corre en la Mac (el token no vive en el server):
    PYTHONPATH=api python3 -m scripts.seo.ga4_social
    PYTHONPATH=api python3 -m scripts.seo.ga4_social --desde 2026-10-01 --hasta 2026-10-28
    PYTHONPATH=api python3 -m scripts.seo.ga4_social --source facebook --campanas
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from app.services import ga4_client

METRICAS = ["sessions", "engagedSessions", "averageSessionDuration", "totalUsers"]


def _informe(desde: str, hasta: str, dimension: str, source: str | None) -> list[dict]:
    body = {
        "dateRanges": [{"startDate": desde, "endDate": hasta}],
        "dimensions": [{"name": dimension}],
        "metrics": [{"name": m} for m in METRICAS],
        "orderBys": [{"metric": {"metricName": "sessions"}, "desc": True}],
        "limit": 100,
    }
    if source:
        body["dimensionFilter"] = {"filter": {
            "fieldName": "sessionSource",
            "stringFilter": {"matchType": "CONTAINS", "value": source, "caseSensitive": False},
        }}
    return ga4_client.run_report(body)


def main() -> int:
    ayer = date.today() - timedelta(days=1)
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--desde", default=(ayer - timedelta(days=29)).isoformat())
    ap.add_argument("--hasta", default=ayer.isoformat())
    ap.add_argument("--source", help="filtra sessionSource que CONTENGA esto (p.ej. facebook)")
    ap.add_argument("--campanas", action="store_true", help="agrupa por utm_campaign")
    args = ap.parse_args()

    try:
        prop = ga4_client.property_id()
        dimension = "sessionCampaignName" if args.campanas else "sessionSourceMedium"
        filas = _informe(args.desde, args.hasta, dimension, args.source)
    except ga4_client.GA4Error as exc:
        print(f"GA4 no disponible: {exc}", file=sys.stderr)
        return 1

    print(f"GA4 propiedad {prop} · {args.desde} → {args.hasta}"
          + (f" · source ~ {args.source}" if args.source else ""))
    print(f"{dimension:45} {'sesiones':>9} {'interac.':>9} {'usuarios':>9} {'dur. media':>10}")
    total = 0
    for f in filas:
        total += int(f["sessions"])
        print(f"{f[dimension][:45]:45} {int(f['sessions']):9} {int(f['engagedSessions']):9} "
              f"{int(f['totalUsers']):9} {float(f['averageSessionDuration']):9.0f}s")
    print(f"{'TOTAL (de las filas listadas)':45} {total:9}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
