"""Auditoría del JSON-LD servido: invariantes, contención frente a la línea base y matriz.

Fase 0 del plan de datos estructurados (12-11-2026). Lee el HTML que sirve la web,
porque el JSON-LD lo montan las páginas de Next al servir: mirar la BD no basta.

Uso:
    # Rastrear prod, guardar el JSON-LD crudo y congelar la línea base
    python -m scripts.seo.audit_jsonld --guardar /tmp/ld --escribir-linea-base \\
        ../data/jsonld/linea_base.json --matriz /tmp/ld/matriz.csv

    # Comprobar (prod o local) contra la línea base y las excepciones declaradas
    python -m scripts.seo.audit_jsonld --linea-base ../data/jsonld/linea_base.json
    python -m scripts.seo.audit_jsonld --base http://localhost:3001 --linea-base …

    # Re-auditar un rastreo guardado sin volver a pedir nada
    python -m scripts.seo.audit_jsonld --desde /tmp/ld

Sale con 1 si hay un fallo nuevo (no declarado en `data/jsonld_excepciones.yaml`)
o si alguna página ha perdido algo de lo que marcaba en la línea base.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.services import jsonld_audit as ja

SITE = "https://entreinteriores.com"
USER_AGENT = "EntreInteriores-Monitor/1.0 (+https://entreinteriores.com)"
HILOS = 3
PAUSA_S = 0.2
# Nodos del sitio que van en todas las páginas: no son la entidad de la página.
_DEL_SITIO = ("/#website", "/#organization")
_TAXONOMIAS = ("temas", "lugares", "conceptos")
_SECCIONES = {"personas": "persona", "grupos": "grupo", "sellos": "sello", "blog": "post",
              "libros": "libro", "estudios": "estudio", "discografia": "discografia"}


def familia(path: str) -> str:
    """Qué clase de página es, por su ruta. Las fichas de disco y canción cuelgan del
    artista: `/extremoduro/agila` y `/extremoduro/agila/so-payaso`."""
    partes = [p for p in path.split("/") if p]
    if not partes:
        return "portada"
    if len(partes) == 1:
        return "artista" if partes[0] in ("extremoduro", "robe") else f"listado:{partes[0]}"
    if partes[0] in _TAXONOMIAS:
        return partes[0].rstrip("s").replace("lugare", "lugar")
    if partes[0] in _SECCIONES:
        return _SECCIONES[partes[0]]
    if partes[0] in ("extremoduro", "robe"):
        return "disco" if len(partes) == 2 else "cancion"
    return f"otra:{partes[0]}"


def urls_del_sitemap(client: httpx.Client, base: str) -> list[str]:
    xml = client.get(f"{base.rstrip('/')}/sitemap.xml", headers={"User-Agent": USER_AGENT}).text
    paths = set()
    for u in re.findall(r"<loc>\s*([^<\s]+)", xml):
        p = ja.norm_id(u, "/")
        paths.add(p if p.startswith("/") else u)
    return sorted(paths)


def rastrear(base: str, limit: int | None) -> dict[str, dict]:
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        rutas = urls_del_sitemap(client, base)[: limit or None]

        def una(path: str) -> tuple[str, dict]:
            for intento in range(2):
                try:
                    r = client.get(base.rstrip("/") + path, headers={"User-Agent": USER_AGENT})
                    return path, {"status": r.status_code, "bloques": ja.bloques(r.text)}
                except httpx.HTTPError as exc:
                    if intento:
                        return path, {"status": 0, "error": str(exc), "bloques": []}
                    time.sleep(2)
                finally:
                    time.sleep(PAUSA_S)
            return path, {"status": 0, "bloques": []}

        with ThreadPoolExecutor(HILOS) as ex:
            return dict(ex.map(una, rutas))


def nodo_principal(pag: ja.Pagina) -> str | None:
    """El nodo de la entidad de la página: el definido con la URL de la página, o el
    primero que no sea del sitio ni una miga."""
    propios = [k for k in pag.definidos if k.split("#")[0] == pag.path
               and not k.endswith(_DEL_SITIO)]
    candidatos = [k for k in propios if "BreadcrumbList" not in pag.definidos[k]]
    return (candidatos or propios or [None])[0]


def matriz(paginas: dict[str, ja.Pagina]) -> list[dict]:
    """Por familia de página y tipo del nodo principal: cuántas páginas llevan cada
    propiedad en ese nodo."""
    cuenta: dict[tuple[str, str], Counter] = defaultdict(Counter)
    total: Counter = Counter()
    for pag in paginas.values():
        principal = nodo_principal(pag)
        tipo = "/".join(pag.definidos.get(principal, [])) if principal else "(sin nodo)"
        k = (familia(pag.path), tipo)
        total[k] += 1
        if principal:
            props = {linea.split(" ", 2)[1] for linea in pag.huella
                     if linea.startswith(principal + " ")}
            cuenta[k].update(props - {"@type"})
    filas = []
    for k in sorted(total):
        for prop, n in sorted(cuenta[k].items(), key=lambda x: (-x[1], x[0])) or [("", 0)]:
            filas.append({"familia": k[0], "tipo_principal": k[1], "paginas": total[k],
                          "propiedad": prop, "con_propiedad": n})
    return filas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=SITE)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--desde", help="carpeta de un rastreo guardado (no pide nada)")
    ap.add_argument("--guardar", help="carpeta donde guardar el JSON-LD crudo")
    ap.add_argument("--linea-base", help="huellas congeladas contra las que comparar")
    ap.add_argument("--escribir-linea-base", help="congelar las huellas de este rastreo")
    ap.add_argument("--matriz", help="CSV de familia × tipo × propiedad")
    ap.add_argument("--excepciones", help="YAML de fallos conocidos (por defecto, data/)")
    ap.add_argument("--fecha-rastreo", help="con --desde: cuándo se hizo aquel rastreo "
                    "(por defecto, ahora)")
    args = ap.parse_args()

    if args.desde:
        crudo = json.loads((Path(args.desde) / "jsonld.json").read_text())
    else:
        crudo = rastrear(args.base, args.limit)
    if args.guardar:
        Path(args.guardar).mkdir(parents=True, exist_ok=True)
        (Path(args.guardar) / "jsonld.json").write_text(
            json.dumps(crudo, ensure_ascii=False, indent=1, sort_keys=True))

    no_200 = sorted(p for p, d in crudo.items() if d["status"] != 200)
    paginas = {p: ja.analizar(d["bloques"], p) for p, d in crudo.items() if d["status"] == 200}
    print(f"{len(crudo)} URLs del sitemap · {len(paginas)} con 200"
          + (f" · sin 200: {', '.join(no_200[:10])}" if no_200 else ""))

    fallos = ja.auditar(paginas, ja.cargar_vocabulario())
    nuevos, conocidos, sobran = ja.separar(fallos, ja.cargar_excepciones(args.excepciones))
    por_regla = Counter(f.regla for f in fallos)
    print(f"fallos: {len(fallos)} ({dict(por_regla)}) · conocidos {len(conocidos)} · "
          f"NUEVOS {len(nuevos)}")
    for f in nuevos[:60]:
        print("  NUEVO", f)
    for e in sobran:
        print(f"  EXCEPCIÓN QUE YA NO CUBRE NADA (quitarla): {e.regla} {e.paths} {e.detalle}")

    perdido: dict[str, list[str]] = {}
    if args.linea_base:
        base = json.loads(Path(args.linea_base).read_text())
        for path, huella in base["huellas"].items():
            if path not in paginas:
                perdido[path] = ["(la página ya no está o no da 200)"]
                continue
            p = ja.perdidas(huella, paginas[path].huella)
            if p:
                perdido[path] = p
        print(f"contención frente a la línea base del {base['fecha']}: "
              f"{len(perdido)} páginas pierden algo")
        for path, p in sorted(perdido.items())[:40]:
            print(f"  PIERDE {path}: {'; '.join(p[:6])}" + (" …" if len(p) > 6 else ""))

    if args.escribir_linea_base:
        Path(args.escribir_linea_base).parent.mkdir(parents=True, exist_ok=True)
        Path(args.escribir_linea_base).write_text(json.dumps({
            "fecha": args.fecha_rastreo or datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            "base": args.base, "urls": len(paginas),
            "huellas": {p: sorted(pag.huella) for p, pag in sorted(paginas.items())},
        }, ensure_ascii=False, indent=1))
        print(f"línea base escrita: {args.escribir_linea_base}")

    if args.matriz:
        filas = matriz(paginas)
        with open(args.matriz, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(filas[0]))
            w.writeheader()
            w.writerows(filas)
        print(f"matriz: {args.matriz} ({len(filas)} filas)")

    if args.guardar:
        (Path(args.guardar) / "fallos.txt").write_text(
            "\n".join(str(f) for f in fallos) + "\n")

    sys.exit(1 if nuevos or perdido else 0)


if __name__ == "__main__":
    main()
