"""Queries de una canción que aterrizan en otra página (fuga de intención).

    python -m scripts.seo.gsc_cannibal
    python -m scripts.seo.gsc_cannibal --min-impresiones 5 --csv /tmp/fuga.csv

Responde a una pregunta que ninguna otra herramienta se hace: cuando alguien
busca «guerrero robe significado», ¿le sale la ficha de la canción o le sale otra
cosa nuestra? `gsc_optimize` mira query→página y `diagnose_page` mira UNA página;
ninguno ve que la impresión la esté cobrando la página equivocada.

Medido el 03-08-2026 con 12 semanas de GSC: **179 queries y 1.633 impresiones**
con 10 clics. De ellas, **81 queries y 418 impresiones son de intención
«significado»**, que es la única que se recupera escribiendo — y la que el corpus
sostiene con dos fuentes.

Tres patrones distintos que conviene no confundir, porque cada uno se arregla de
otra manera:

- **Temáticas que cobran el significado de una canción**: `/conceptos/el-espejo`
  se lleva «por encima del bien y del mal robe significado». Se arregla con un
  `##` en la ficha de la canción.
- **Versiones de la misma canción compitiendo entre sí**: `jesucristo-garcia`
  pierde 89 impresiones contra su propia versión en directo y la del debut. Eso
  no es fuga, es canibalización interna: se arregla decidiendo qué versión es la
  canónica, no escribiendo más.
- **Navegacional que cae en la home**: «entre interiores» es a la vez el nombre
  del sitio y el de una canción. Que la home rankee ahí es correcto; solo hay que
  recuperar las variantes con intención («entre interiores significado»).

No escribe nada: es un informe para decidir dónde meter un `##` y dónde un
enlace interno.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import select  # noqa: E402

from app.db.models import Album, Artist, Song  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

GSC_PATH = Path(os.environ.get("GSC_PAGE_QUERIES", "/app/data/gsc_page_queries.json"))

# Un título corto ('Mama', 'Puta', 'Salir') aparece en cualquier frase, así que
# por sí solo no prueba nada: se exige que la query nombre además al artista.
# Mismo criterio que la guarda de `kw_attribute`, y por el mismo motivo.
MIN_TITULO_INEQUIVOCO = 8
MARCAS = ("extremoduro", "robe", "roberto iniesta", "iniesta")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ\s]", " ", s)).strip()


def _intencion(q: str) -> str:
    """Para qué se busca. Decide si la fuga es recuperable escribiendo."""
    if re.search(r"signific|que quiere decir|de que (habla|trata)|explicac|interpretac", q):
        return "significado"
    if re.search(r"\bletra|lyrics", q):
        return "letra"
    if re.search(r"acorde|tablatur|\btabs?\b", q):
        return "acordes"
    return "otra"


def cargar_canciones(db) -> list[tuple[str, str, str]]:
    """(titulo_normalizado, ruta, slug) de cada canción del catálogo."""
    out = []
    filas = db.execute(
        select(Song, Album, Artist)
        .join(Album, Song.album_id == Album.id)
        .join(Artist, Album.artist_id == Artist.id)
    ).all()
    for s, al, ar in filas:
        limpio = norm(re.sub(r"\s*\(.*?\)", "", s.title))
        if limpio:
            out.append((limpio, f"/{ar.slug}/{al.slug}/{s.slug}", s.slug))
    # Título más largo primero: «historias prohibidas» debe ganar a «historias».
    out.sort(key=lambda x: -len(x[0]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-impresiones", type=int, default=1,
                    help="suelo de impresiones (default 1: en un sitio de nicho "
                         "lo valioso vive muy abajo)")
    ap.add_argument("--csv", help="volcar el detalle a este fichero")
    ap.add_argument("--solo-recuperables", action="store_true",
                    help="solo las intenciones que se pueden servir escribiendo "
                         "(significado); deja fuera letra y acordes")
    args = ap.parse_args()

    if not GSC_PATH.exists():
        print(f"No hay datos de GSC en {GSC_PATH}", file=sys.stderr)
        return 1
    data = json.loads(GSC_PATH.read_text(encoding="utf-8"))
    per = data.get("period") or {}

    db = SessionLocal()
    try:
        canciones = cargar_canciones(db)
    finally:
        db.close()

    fugas = []
    for url, queries in (data.get("pages") or {}).items():
        for q in queries:
            texto = q.get("query") or ""
            nq = norm(texto)
            imp = int(q.get("impressions", 0))
            if imp < args.min_impresiones:
                continue
            for titulo, ruta, slug in canciones:
                if titulo not in nq:
                    continue
                # Título corto: solo cuenta si la query nombra al artista.
                if len(titulo) < MIN_TITULO_INEQUIVOCO and not any(m in nq for m in MARCAS):
                    continue
                if url.rstrip("/") == ruta.rstrip("/"):
                    break          # aterriza donde debe: no es fuga
                fugas.append({
                    "query": texto, "impresiones": imp,
                    "posicion": q.get("position"), "clics": int(q.get("clicks", 0)),
                    "aterriza_en": url, "deberia_ser": ruta, "slug": slug,
                    "intencion": _intencion(nq),
                })
                break

    if args.solo_recuperables:
        fugas = [f for f in fugas if f["intencion"] == "significado"]
    fugas.sort(key=lambda f: -f["impresiones"])

    if args.csv:
        with open(args.csv, "w", encoding="utf-8", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=list(fugas[0].keys()) if fugas else
                                ["query", "impresiones", "posicion", "clics",
                                 "aterriza_en", "deberia_ser", "slug", "intencion"])
            wr.writeheader()
            wr.writerows(fugas)

    total_imp = sum(f["impresiones"] for f in fugas)
    total_clics = sum(f["clics"] for f in fugas)
    print(f"\n{'='*78}")
    print("  FUGA DE INTENCIÓN — queries de una canción que cobra otra página")
    print(f"  periodo {per.get('start','?')} → {per.get('end','?')}")
    print(f"{'='*78}")
    print(f"  {len(fugas)} queries · {total_imp} impresiones · {total_clics} clics\n")

    por_intencion: dict[str, list] = defaultdict(list)
    for f in fugas:
        por_intencion[f["intencion"]].append(f)
    print(f"  {'INTENCIÓN':<14} {'QUERIES':>8} {'IMPR':>7}   ¿se puede servir?")
    print(f"  {'-'*70}")
    servible = {"significado": "sí, escribiendo un bloque",
                "letra": "no en abierto: la letra vive tras registro",
                "acordes": "no: el sitio no publica acordes",
                "otra": "según el caso"}
    for nombre in ("significado", "letra", "acordes", "otra"):
        fs = por_intencion.get(nombre) or []
        if fs:
            print(f"  {nombre:<14} {len(fs):>8} {sum(x['impresiones'] for x in fs):>7}   "
                  f"{servible[nombre]}")

    # Por canción: es la unidad de trabajo, no la query suelta.
    por_cancion: dict[str, list] = defaultdict(list)
    for f in fugas:
        por_cancion[f["deberia_ser"]].append(f)
    ranking = sorted(por_cancion.items(),
                     key=lambda kv: -sum(x["impresiones"] for x in kv[1]))
    print(f"\n  {'-'*70}")
    print("  POR CANCIÓN, por impresiones perdidas:\n")
    for ruta, fs in ranking[:20]:
        imp = sum(x["impresiones"] for x in fs)
        ladrones = sorted({x["aterriza_en"] for x in fs})
        mejor = min((x["posicion"] for x in fs if x["posicion"]), default=None)
        print(f"  {imp:>5} impr · {len(fs):>2} queries · mejor pos "
              f"{mejor if mejor else '—'}   {ruta}")
        print(f"        se las lleva: {', '.join(ladrones[:3])}")
        for x in sorted(fs, key=lambda y: -y["impresiones"])[:2]:
            print(f"        «{x['query']}» ({x['intencion']})")
        print()
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
