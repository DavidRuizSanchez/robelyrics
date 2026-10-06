"""Recorre setlist.fm con un navegador real y saca lo que el HTTP plano no da.

    python -m scripts.pr.crawl_setlist_browser --out DIR --what anios,giras
    python -m scripts.pr.crawl_setlist_browser --out DIR --what conciertos,canciones

Corre en LOCAL (la Mac), no en el contenedor: necesita Playwright y Chromium, y la
IP residencial. Decisión de David (06-10-2026): se recorre su índice con atribución
y sin pedirles permiso. Mitigaciones que sí se aplican — `PAUSA` de 3,5 s, que es su
propio límite, y nada de su dato en nuestra BD ni en git.

POR QUÉ UN NAVEGADOR Y NO `httpx`
---------------------------------
Dos razones distintas, y conviene no confundirlas:

1. Las URLs con query string (`?year=`, `?tour=`) devuelven **202 con 0 bytes** a un
   cliente HTTP: es el WAF de AWS. Tras unas pocas peticiones seguidas corta también
   la página base.
2. **Y aunque pasaran, el HTML de llegada viene SIN HIDRATAR.** Esto me costó una
   conclusión falsa: midiendo la página de la gira «Agila 96» con `httpx` salía que
   declaraba 53 conciertos y que su canción más tocada tenía 4 toques, y lo di por
   «sus desgloses por gira no son fiables». No era su dato, era mi medición. Con el
   navegador esperando a `tr.songRow`, el año 2008 pasa de 0 a **1.011 toques en 47
   conciertos** (21,5 por concierto, que es un repertorio completo).

De ahí la regla del módulo: **nunca se lee la página sin esperar a su tabla**, y si la
tabla no aparece se marca `incompleto` en vez de devolver cero. Un cero silencioso
aquí es lo que convierte un agujero de medición en un hallazgo publicado.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.pr.setlist_parse import parse_artista  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE = "https://www.setlist.fm"
PAUSA_MS = 3500          # su límite: 1 petición cada 3 s
ESPERA_TABLA_MS = 15000

ARTISTAS = (("extremoduro", "extremoduro-13d68da1"), ("robe", "robe-63c74607"))

# Un concierto en el índice: <div class="col-xs-12 setlistPreview"> … con
# <div class="dateBlock"> (mes/día/año en spans) y el enlace al setlist, cuyo
# texto lleva «at <recinto>, <ciudad>, <país>».
_FECHA = re.compile(
    r'<span class="month">(\w+)</span>\s*<span class="day">(\d+)</span>\s*<span class="year">(\d{4})</span>',
    re.S)
_MESES = {m: i for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], 1)}


def _texto(frag: str) -> str:
    import html as H
    return H.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", frag))).strip()


def parse_conciertos(doc: str) -> list[dict]:
    """Un dict por concierto del índice: fecha, recinto, ciudad, país."""
    salida = []
    for bloque in re.findall(r'class="col-xs-12 setlistPreview"(.*?)(?=class="col-xs-12 setlistPreview"|$)',
                             doc, re.S):
        f = _FECHA.search(bloque)
        fecha = None
        if f:
            mes = _MESES.get(f.group(1)[:3].title())
            if mes:
                fecha = f"{f.group(3)}-{mes:02d}-{int(f.group(2)):02d}"
        # «… at Palau Sant Jordi, Barcelona, Spain»
        sitio = re.search(r'<a[^>]*class="summary[^"]*"[^>]*>(.*?)</a>', bloque, re.S)
        lugar = _texto(sitio.group(1)) if sitio else ""
        if not lugar:
            cab = re.search(r'<h2[^>]*>(.*?)</h2>', bloque, re.S)
            lugar = _texto(cab.group(1)) if cab else ""
        partes = [p.strip() for p in lugar.split(" at ")[-1].split(",") if p.strip()]
        salida.append({
            "fecha": fecha,
            "recinto": partes[0] if len(partes) >= 3 else (partes[0] if partes else None),
            "ciudad": partes[-2] if len(partes) >= 2 else None,
            "pais": partes[-1] if len(partes) >= 2 else None,
            "literal": lugar[:160],
        })
    return salida


def _abrir(pg, url: str, selector: str | None) -> tuple[str, bool]:
    """Devuelve (html, completo). `completo=False` si la tabla no llegó."""
    pg.goto(url, wait_until="networkidle", timeout=60000)
    if not selector:
        return pg.content(), True
    try:
        pg.wait_for_selector(selector, timeout=ESPERA_TABLA_MS)
        return pg.content(), True
    except Exception:
        return pg.content(), False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--what", default="anios,giras",
                    help="anios,giras,conciertos,canciones")
    ap.add_argument("--max-paginas", type=int, default=60)
    args = ap.parse_args()
    quiere = {w.strip() for w in args.what.split(",")}
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    datos: dict = {"generado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "atribucion": {"fuente": "setlist.fm", "sin_nofollow": True},
                   "artistas": {}}
    incompletos: list[str] = []

    with sync_playwright() as p:
        nav = p.chromium.launch(headless=True)
        ctx = nav.new_context(locale="es-ES", viewport={"width": 1366, "height": 900})
        pg = ctx.new_page()

        for slug, sid in ARTISTAS:
            d = datos["artistas"].setdefault(slug, {})

            # la página base da la lista de años y de giras (y sus ids)
            doc, _ = _abrir(pg, f"{BASE}/stats/{sid}.html", "tr.songRow")
            base = parse_artista(doc, slug)
            d["setlists"] = base.setlists
            d["anyos_declarados"] = list(base.anyos)
            d["giras_declaradas"] = list(base.giras)
            ids_gira = dict(re.findall(r'href="[^"]*\?tour=([0-9a-f]+)"\s+title="Show song statistics of the tour ([^"]+)"', doc))
            pg.wait_for_timeout(PAUSA_MS)

            if "anios" in quiere:
                d["por_anyo"] = {}
                for anyo, n in base.anyos:
                    doc, ok = _abrir(pg, f"{BASE}/stats/{sid}.html?year={anyo}", "tr.songRow")
                    a = parse_artista(doc, slug)
                    d["por_anyo"][anyo] = {
                        "setlists": n, "canciones": len(a.canciones),
                        "toques": a.toques_totales, "completo": ok,
                        "detalle": [{"titulo": c.titulo, "toques": c.toques} for c in a.canciones],
                    }
                    if not ok:
                        incompletos.append(f"{slug} año {anyo}")
                    logger.info("%s %s: %d canciones · %d toques%s",
                                slug, anyo, len(a.canciones), a.toques_totales,
                                "" if ok else "  ← INCOMPLETO")
                    pg.wait_for_timeout(PAUSA_MS)

            if "giras" in quiere:
                d["por_gira"] = {}
                for gid, nombre in ids_gira.items():
                    doc, ok = _abrir(pg, f"{BASE}/stats/{sid}.html?tour={gid}", "tr.songRow")
                    a = parse_artista(doc, slug)
                    d["por_gira"][nombre] = {
                        "canciones": len(a.canciones), "toques": a.toques_totales,
                        "completo": ok,
                        "detalle": [{"titulo": c.titulo, "toques": c.toques} for c in a.canciones],
                    }
                    if not ok:
                        incompletos.append(f"{slug} gira {nombre}")
                    logger.info("%s «%s»: %d canciones · %d toques%s",
                                slug, nombre, len(a.canciones), a.toques_totales,
                                "" if ok else "  ← INCOMPLETO")
                    pg.wait_for_timeout(PAUSA_MS)

            if "conciertos" in quiere:
                todos, pagina = [], 1
                while pagina <= args.max_paginas:
                    url = f"{BASE}/setlists/{sid}.html" + ("" if pagina == 1 else f"?page={pagina}")
                    doc, _ = _abrir(pg, url, ".setlistPreview")
                    lote = parse_conciertos(doc)
                    if not lote:
                        break
                    todos += lote
                    logger.info("%s conciertos p%d: +%d (total %d)", slug, pagina, len(lote), len(todos))
                    pagina += 1
                    pg.wait_for_timeout(PAUSA_MS)
                d["conciertos"] = todos

        nav.close()

    datos["incompletos"] = incompletos
    destino = out / "setlist_browser.json"
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    logger.info("escrito %s", destino)

    # --- validación: los toques por año deben sumar el total del artista ---
    print()
    for slug, d in datos["artistas"].items():
        tot = d.get("setlists")
        if "por_anyo" in d:
            suma_a = sum(v["toques"] for v in d["por_anyo"].values())
            print(f"{slug}: {tot} setlists · toques sumando años = {suma_a}")
        if "por_gira" in d:
            suma_g = sum(v["toques"] for v in d["por_gira"].values())
            print(f"{slug}: toques sumando giras = {suma_g}")
        if "conciertos" in d:
            c = d["conciertos"]
            print(f"{slug}: {len(c)} conciertos · con fecha {sum(1 for x in c if x['fecha'])} "
                  f"· con ciudad {sum(1 for x in c if x['ciudad'])}")
    if incompletos:
        print(f"\n⚠ {len(incompletos)} páginas incompletas (tabla no cargó): {incompletos[:6]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
