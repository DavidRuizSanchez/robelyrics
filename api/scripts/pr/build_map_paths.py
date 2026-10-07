"""Convierte el GeoJSON de provincias en trazados SVG listos para incrustar.

    python -m scripts.pr.build_map_paths --geojson X.geojson --out mapa.json

El GeoJSON de partida trae 30.231 puntos y 1,3 MB: incrustarlo tal cual en una
página es inviable. Aquí se proyecta, se simplifica con Douglas-Peucker y se
escupe un trazado por provincia con las coordenadas ya en el espacio del SVG.

Dos decisiones que no son cosméticas:

  · **Canarias va en recuadro aparte.** Está a 1.800 km y 7 grados de longitud del
    resto; dibujarla en su sitio real obliga a un lienzo donde la Península ocupa
    un tercio y el resto es océano. Se traslada a una caja propia, como en
    cualquier mapa de España, y el recuadro se dibuja para que se vea que es un
    inserto y no geografía.
  · **La simplificación mantiene la forma, no cada entrante.** Douglas-Peucker con
    tolerancia en grados; las islas y los trozos minúsculos se descartan por área
    para que no queden puntos sueltos flotando.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import unicodedata
from pathlib import Path

# El GeoJSON usa nombres bilingües y alguna grafía propia. A la izquierda lo suyo
# normalizado, a la derecha el nombre que usamos nosotros.
NOMBRES = {
    "alacant alicante": "Alicante", "araba alava": "Álava",
    "bizkaia vizcaya": "Vizcaya", "castello castellon": "Castellón",
    "gipuzkoa guipuzcoa": "Guipúzcoa", "illes balears": "Baleares",
    "valencia valencia": "Valencia", "santa cruz de tenerife": "Santa Cruz de Tenerife",
}
# Fuera del mapa: no hubo conciertos y meterlas alarga el lienzo.
FUERA = {"ceuta", "melilla"}

CANARIAS = {"Las Palmas", "Santa Cruz de Tenerife"}

ANCHO, ALTO = 1000.0, 720.0
MARGEN = 14.0
TOLERANCIA = 0.012      # grados; ~1,3 km. Mantiene la silueta y quita el ruido
AREA_MINIMA = 0.0015    # grados²; por debajo es una isla que no se vería


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower().replace("/", " "))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


def provincia(nombre: str) -> str | None:
    n = _norm(nombre)
    if n in FUERA:
        return None
    return NOMBRES.get(n, nombre.strip())


def _perp(p, a, b) -> float:
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def simplificar(pts: list, tol: float) -> list:
    """Douglas-Peucker iterativo (sin recursión: hay anillos de miles de puntos)."""
    if len(pts) < 3:
        return pts
    guardar = [False] * len(pts)
    guardar[0] = guardar[-1] = True
    pila = [(0, len(pts) - 1)]
    while pila:
        i, j = pila.pop()
        if j <= i + 1:
            continue
        peor, idx = 0.0, i
        for k in range(i + 1, j):
            d = _perp(pts[k], pts[i], pts[j])
            if d > peor:
                peor, idx = d, k
        if peor > tol:
            guardar[idx] = True
            pila += [(i, idx), (idx, j)]
    return [p for p, g in zip(pts, guardar) if g]


def area(pts: list) -> float:
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def anillos(geom: dict) -> list:
    t, c = geom["type"], geom["coordinates"]
    if t == "Polygon":
        return [c[0]]
    if t == "MultiPolygon":
        return [poly[0] for poly in c]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--geojson", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    datos = json.loads(Path(args.geojson).read_text(encoding="utf-8"))

    # 1) recoger anillos simplificados en grados, separando Canarias
    crudo: dict[str, list] = {}
    for f in datos["features"]:
        prov = provincia(f["properties"]["name"])
        if not prov:
            continue
        for anillo in anillos(f["geometry"]):
            pts = [(float(x), float(y)) for x, y in anillo]
            if area(pts) < AREA_MINIMA:
                continue
            s = simplificar(pts, TOLERANCIA)
            if len(s) >= 4:
                crudo.setdefault(prov, []).append(s)

    peninsula = {p: a for p, a in crudo.items() if p not in CANARIAS}
    canarias = {p: a for p, a in crudo.items() if p in CANARIAS}

    def caja(grupo):
        xs = [x for anillos_ in grupo.values() for a in anillos_ for x, _ in a]
        ys = [y for anillos_ in grupo.values() for a in anillos_ for _, y in a]
        return min(xs), max(xs), min(ys), max(ys)

    # 2) proyección equirectangular corregida por la latitud media
    x0, x1, y0, y1 = caja(peninsula)
    k = math.cos(math.radians((y0 + y1) / 2))
    ancho_g, alto_g = (x1 - x0) * k, (y1 - y0)
    escala = min((ANCHO - 2 * MARGEN) / ancho_g, (ALTO * 0.80 - 2 * MARGEN) / alto_g)
    despl_x = MARGEN + ((ANCHO - 2 * MARGEN) - ancho_g * escala) / 2

    def proy(x, y):
        return ((x - x0) * k * escala + despl_x, (y1 - y) * escala + MARGEN)

    # 3) Canarias, a su caja
    cx0, cx1, cy0, cy1 = caja(canarias)
    ck = math.cos(math.radians((cy0 + cy1) / 2))
    caja_w, caja_h = 236.0, 104.0
    caja_x, caja_y = MARGEN + 4, ALTO - caja_h - MARGEN
    cesc = min(caja_w / ((cx1 - cx0) * ck), caja_h / (cy1 - cy0)) * 0.92

    def proy_can(x, y):
        return (caja_x + (x - cx0) * ck * cesc + 6, caja_y + (cy1 - y) * cesc + 6)

    # 4) trazados
    def trazar(anillos_, f):
        partes = []
        for a in anillos_:
            d = " ".join(
                ("M" if i == 0 else "L") + f"{px:.1f} {py:.1f}"
                for i, (px, py) in enumerate(f(x, y) for x, y in a)
            )
            partes.append(d + "Z")
        return "".join(partes)

    paths = {p: trazar(a, proy) for p, a in peninsula.items()}
    paths.update({p: trazar(a, proy_can) for p, a in canarias.items()})

    salida = {
        "viewBox": f"0 0 {ANCHO:.0f} {ALTO:.0f}",
        "inset_canarias": {"x": caja_x, "y": caja_y, "w": caja_w + 12, "h": caja_h + 12},
        "paths": paths,
        "fuente": "Provincias de España · codeforgermany/click_that_hood (datos públicos)",
    }
    Path(args.out).write_text(json.dumps(salida, ensure_ascii=False), encoding="utf-8")
    n = sum(d.count("L") + d.count("M") for d in paths.values())
    print(f"{len(paths)} provincias · {n} puntos · {Path(args.out).stat().st_size//1024} KB")
    faltan = sorted(set(paths) - set(peninsula) - set(canarias))
    if faltan:
        print("sin clasificar:", faltan)
    return 0


if __name__ == "__main__":
    sys.exit(main())
