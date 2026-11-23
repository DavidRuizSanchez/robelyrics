"""Ventanas de GSC para el seguimiento de las fusiones (23-11-2026).

Dos pasos, porque el token de GSC vive solo en la Mac (ver infra/local/gsc_weekly.sh):

  exportar   (PROD) Qué fusiones tienen ya sus 4 semanas de después y sin mirar. JSON a stdout.
  descargar  (MAC)  Para cada una, las consultas y los totales de su página en las 4
                    semanas de antes y en las 4 de después.

El cálculo y el correo los hace `seo_queue --watch` en prod, que lee lo descargado
de `data/merge_watch_gsc.json`.

Uso:
  python -m scripts.seo.merge_watch exportar > fusiones.json
  python -m scripts.seo.merge_watch descargar --fusiones fusiones.json --out merge_watch_gsc.json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    stream=sys.stderr)
logger = logging.getLogger(__name__)

SITE = "https://entreinteriores.com"


def cmd_exportar(_args) -> None:
    from app.db.session import SessionLocal
    from app.services import merge_watch

    with SessionLocal() as db:
        fusiones = merge_watch.pendientes(db)
    json.dump(fusiones, sys.stdout, ensure_ascii=False)
    logger.info("%d fusiones listas para medir", len(fusiones))


def _ventana(gsc_client, path: str, desde: str, hasta: str) -> dict:
    filtro = [{"filters": [{"dimension": "page", "operator": "equals",
                            "expression": SITE + path}]}]
    base = {"startDate": desde, "endDate": hasta, "dimensionFilterGroups": filtro}
    consultas = gsc_client.search_analytics({**base, "dimensions": ["query"],
                                             "rowLimit": 25000})
    total = gsc_client.search_analytics({**base, "dimensions": ["page"]})
    t = total[0] if total else {}
    # El sitio entero en las mismas fechas: sin él, un -37 % de la página no se sabe
    # si es de la fusión o de que todo el sitio ha bajado.
    sitio = gsc_client.search_analytics({"startDate": desde, "endDate": hasta,
                                         "dimensions": ["country"], "rowLimit": 300})
    return {
        "sitio": {"clicks": sum(int(r.get("clicks", 0)) for r in sitio),
                  "impressions": sum(int(r.get("impressions", 0)) for r in sitio)},
        "desde": desde, "hasta": hasta,
        "consultas": [{"query": r["keys"][0], "clicks": int(r.get("clicks", 0)),
                       "impressions": int(r.get("impressions", 0)),
                       "position": round(float(r.get("position", 0)), 1)}
                      for r in consultas],
        # Los totales van aparte: la suma por consulta deja fuera las anónimas.
        "pagina": {"clicks": int(t.get("clicks", 0)),
                   "impressions": int(t.get("impressions", 0))},
    }


def cmd_descargar(args) -> None:
    from app.services import gsc_client

    fusiones = json.loads(Path(args.fusiones).read_text(encoding="utf-8"))
    datos: dict = {"fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
                   "fusiones": {}}
    for f in fusiones:
        antes = _ventana(gsc_client, f["path"], *f["antes"])
        despues = _ventana(gsc_client, f["path"], *f["despues"])
        if not antes["pagina"]["impressions"] and not despues["pagina"]["impressions"]:
            # Sin una sola impresión en ocho semanas lo más probable es el token, no la
            # página: no se escribe nada que pueda pasar por «no ha caído nada».
            logger.warning("%s: GSC no devuelve nada en ninguna ventana; se omite", f["path"])
            continue
        datos["fusiones"][str(f["id"])] = {"path": f["path"], "antes": antes,
                                           "despues": despues}
        logger.info("%s: %d consultas antes, %d después", f["path"],
                    len(antes["consultas"]), len(despues["consultas"]))
    Path(args.out).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    logger.info("escrito %s (%d fusiones)", args.out, len(datos["fusiones"]))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("exportar")
    d = sub.add_parser("descargar")
    d.add_argument("--fusiones", required=True)
    d.add_argument("--out", required=True)
    args = ap.parse_args()
    {"exportar": cmd_exportar, "descargar": cmd_descargar}[args.cmd](args)


if __name__ == "__main__":
    main()
