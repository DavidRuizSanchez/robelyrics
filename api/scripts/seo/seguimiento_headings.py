"""Seguimiento a 1, 2, 3 y 4 semanas de los headings humanizados (11-11-2026).

Tres pasos, porque el token de GSC vive solo en la Mac (ver infra/local/gsc_weekly.sh):

  exportar   (PROD) Qué páginas se cambiaron y cuándo, de `content_revisions`. JSON a stdout.
  descargar  (MAC)  GSC page+date, page+query+date e inspección de URL de esas páginas.
  informe    (PROD) Si hay una semana con datos sin mandar, la calcula y la manda a
                    ADMIN_EMAIL. El estado y el archivo los guarda la Mac.

Lo orquesta infra/local/seguimiento_headings.sh, que lanza launchd cada día. El
informe solo sale cuando GSC ya tiene la semana entera, así que da igual que la Mac
pase días dormida. Tras la semana 4 no hace nada más.

Uso:
  python -m scripts.seo.seguimiento_headings exportar > cambios.json
  python -m scripts.seo.seguimiento_headings descargar --cambios cambios.json --out gsc.json
  python -m scripts.seo.seguimiento_headings informe --enviadas 1,2 [--semana 3] [--no-email]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    stream=sys.stderr)
logger = logging.getLogger(__name__)

SITE = "https://entreinteriores.com"
LAG_DIAS = 3  # GSC con dataState final no trae los últimos ~3 días
MARGEN_ANTES = 7 * 4 + 2
REASON = "headings humanos%"


def _dir_datos() -> Path:
    for p in (Path("/app/data"), Path(__file__).resolve().parents[3] / "data"):
        if p.exists():
            return p / "seguimiento_headings"
    raise SystemExit("no encuentro data/")


# ------------------------------------------------------------------ exportar

def cmd_exportar(_args) -> None:
    from sqlalchemy import text

    from app.db.session import SessionLocal

    db = SessionLocal()
    filas = db.execute(text(
        "select r.path, min(r.created_at), max(r.created_at), max(s.entity_type) "
        "from content_revisions r left join seo_content s "
        "  on r.target_kind = 'seo_content' and s.id = r.target_id "
        "where r.reason like :reason group by r.path"), {"reason": REASON}).fetchall()
    cambios = {p: {"primero": a.isoformat(), "ultimo": b.isoformat(), "tipo": t}
               for p, a, b, t in filas}
    json.dump(cambios, sys.stdout, ensure_ascii=False)
    logger.info("%d páginas con headings cambiados", len(cambios))


# ------------------------------------------------------------------ descargar

def _path(url: str) -> str:
    return (url[len(SITE):] or "/") if url.startswith(SITE) else url


def _paginado(gsc_client, body: dict) -> list[dict]:
    filas, inicio = [], 0
    while True:
        lote = gsc_client.search_analytics({**body, "rowLimit": 25000, "startRow": inicio})
        filas += lote
        if len(lote) < 25000:
            return filas
        inicio += 25000


def _inspeccionar(gsc_client, paths: list[str]) -> dict:
    """lastCrawlTime de cada página. Cada llamada tarda ~7 s (medido el 11-11-2026),
    así que van en paralelo: la cuota es de 600 por minuto y 2.000 al día."""
    from concurrent.futures import ThreadPoolExecutor

    import httpx

    token = gsc_client._access_token()  # noqa: SLF001 — mismo token, otro endpoint
    if not token:
        logger.warning("sin token: no se inspecciona el rastreo")
        return {}

    def una(path: str):
        try:
            r = httpx.post(
                "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
                headers={"Authorization": f"Bearer {token}"},
                json={"inspectionUrl": SITE + path, "siteUrl": gsc_client.SITE_URL},
                timeout=90)
            r.raise_for_status()
            idx = r.json().get("inspectionResult", {}).get("indexStatusResult", {})
            return path, {"lastCrawlTime": idx.get("lastCrawlTime"),
                          "coverageState": idx.get("coverageState")}
        except Exception as exc:  # noqa: BLE001
            logger.warning("inspección de %s falló: %s", path, exc)
            return path, None

    with ThreadPoolExecutor(max_workers=8) as pool:
        return {p: info for p, info in pool.map(una, paths) if info}


def _inspeccion_al_dia(gsc_client, cambios: dict, salida: Path) -> dict:
    """Reaprovecha la pasada anterior: lo ya rastreado tras el cambio no se reinspecciona.

    Cada inspección tarda ~2 s y la cuota es de 2.000 al día; inspeccionar las 272
    páginas a diario costaría 10 minutos para volver a saber lo que ya se sabía.
    """
    previa = {}
    if salida.exists():
        try:
            previa = json.loads(salida.read_text(encoding="utf-8")).get("inspeccion") or {}
        except (OSError, ValueError):
            previa = {}
    hecho = {p: i for p, i in previa.items()
             if p in cambios and i.get("lastCrawlTime")
             and i["lastCrawlTime"][:10] > cambios[p]["ultimo"][:10]}
    pendientes = sorted(p for p in cambios if p not in hecho)
    logger.info("inspección: %d ya rastreadas tras el cambio, %d por mirar",
                len(hecho), len(pendientes))
    return {**hecho, **_inspeccionar(gsc_client, pendientes)}


def cmd_descargar(args) -> None:
    from app.services import gsc_client

    cambios = json.loads(Path(args.cambios).read_text(encoding="utf-8"))
    if not cambios:
        raise SystemExit("no hay cambios que medir")
    primero = min(date.fromisoformat(c["primero"][:10]) for c in cambios.values())
    inicio = primero - timedelta(days=MARGEN_ANTES)
    fin = date.today() - timedelta(days=LAG_DIAS)
    rango = {"startDate": inicio.isoformat(), "endDate": fin.isoformat()}

    pd = _paginado(gsc_client, {**rango, "dimensions": ["page", "date"]})
    pqd = _paginado(gsc_client, {**rango, "dimensions": ["page", "query", "date"]})
    sitio = gsc_client.search_analytics({**rango, "dimensions": ["date"]})
    if not pd:
        raise SystemExit("GSC no devolvió filas (¿token caducado?)")
    fin_real = max(r["keys"][1] for r in pd)
    datos = {
        "site": gsc_client.SITE_URL,
        "inicio": inicio.isoformat(), "fin": fin_real,
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "page_daily": [[_path(r["keys"][0]), r["keys"][1], r["clicks"], r["impressions"],
                        r["position"]] for r in pd],
        "page_query_daily": [[_path(r["keys"][0]), r["keys"][1], r["keys"][2], r["clicks"],
                              r["impressions"], r["position"]] for r in pqd],
        "site_daily": [[r["keys"][0], r["clicks"], r["impressions"]] for r in sitio],
        "inspeccion": {} if args.sin_inspeccion else _inspeccion_al_dia(gsc_client, cambios,
                                                                          Path(args.out)),
    }
    Path(args.out).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    logger.info("GSC %s → %s: %d filas page+date, %d page+query+date, %d inspecciones",
                inicio, fin_real, len(pd), len(pqd), len(datos["inspeccion"]))


# ------------------------------------------------------------------ informe

def _validacion(gsc: dict, res: dict) -> dict:
    """Total del sitio (consulta por fecha, independiente) frente a la suma por página."""
    (a0, _), (_, d1) = res["ventana_control"]
    suma = sum(r[2] for r in gsc["page_daily"] if a0.isoformat() <= r[1] <= d1.isoformat())
    total = sum(r[1] for r in gsc.get("site_daily") or []
                if a0.isoformat() <= r[0] <= d1.isoformat())
    return {"suma_paginas": suma, "total_sitio": total,
            "periodo": f"{a0.isoformat()}..{d1.isoformat()}"}


def cmd_informe(args) -> None:
    """Calcula la semana pendiente, la manda y la imprime tras una línea «SEMANA k».

    No escribe nada en prod: allí `data/` va montado en solo lectura. El estado (qué
    semanas se han mandado) y el archivo de informes los guarda la Mac, que es quien
    orquesta, y le pasa aquí lo ya enviado con `--enviadas`.
    """
    from app.services import seguimiento_headings as sh

    carpeta = Path(args.dir) if args.dir else _dir_datos()
    cambios = json.loads((carpeta / "cambios.json").read_text(encoding="utf-8"))
    gsc = json.loads((carpeta / "gsc.json").read_text(encoding="utf-8"))
    enviadas = [x for x in (args.enviadas or "").split(",") if x.strip()]

    k = args.semana or sh.semana_pendiente(cambios, gsc["fin"], enviadas)
    if not k:
        logger.info("nada que mandar (datos hasta %s; enviadas: %s)", gsc["fin"],
                    enviadas or "ninguna")
        return
    if not sh.semana_cubierta(cambios, gsc["fin"], k) and not args.force:
        raise SystemExit(f"los datos (hasta {gsc['fin']}) no cubren la semana {k}")

    res = sh.analizar(cambios, gsc, k)
    meta = {
        "site": gsc["site"], "fin": gsc["fin"], "fetched_at": gsc["fetched_at"],
        "primer_cambio": min(c["primero"][:10] for c in cambios.values()),
        "ultimo_cambio": max(c["ultimo"][:10] for c in cambios.values()),
        "validacion": _validacion(gsc, res),
    }
    texto = sh.informe_texto(res, meta)
    if args.guardar:
        (carpeta / f"semana_{k}.txt").write_text(texto, encoding="utf-8")
        _csv(carpeta / f"semana_{k}_consultas.csv", res["protegidas"])
        _csv(carpeta / f"semana_{k}_paginas.csv", res["paginas"])

    if not args.no_email:
        from app.config import get_settings
        from app.services.email import send_email

        to = get_settings().admin_email
        if not to:
            raise SystemExit("sin ADMIN_EMAIL: no se manda nada")
        send_email(to=to, subject=sh.asunto(res), html=sh.informe_html(texto), text=texto)
        logger.info("semana %d enviada a %s", k, to)
    print(f"SEMANA {k}")
    print(texto)


def _csv(path: Path, filas: list[dict]) -> None:
    import csv

    if not filas:
        path.write_text("", encoding="utf-8")
        return
    campos = list(dict.fromkeys(k for f in filas for k in f))
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("exportar")
    d = sub.add_parser("descargar")
    d.add_argument("--cambios", required=True)
    d.add_argument("--out", required=True)
    d.add_argument("--sin-inspeccion", action="store_true")
    i = sub.add_parser("informe")
    i.add_argument("--semana", type=int, choices=(1, 2, 3, 4))
    i.add_argument("--no-email", action="store_true")
    i.add_argument("--force", action="store_true")
    i.add_argument("--enviadas", help="semanas ya mandadas, p. ej. 1,2")
    i.add_argument("--dir", help="carpeta con cambios.json y gsc.json")
    i.add_argument("--guardar", action="store_true", help="escribe .txt y .csv en --dir")
    args = ap.parse_args()
    {"exportar": cmd_exportar, "descargar": cmd_descargar, "informe": cmd_informe}[args.cmd](args)


if __name__ == "__main__":
    main()
