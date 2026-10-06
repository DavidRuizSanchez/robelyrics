"""Geografía del directo: ciudades, recintos y países, desde el índice de conciertos.

    python -m scripts.pr.analyze_geography --browser DIR/setlist_browser.json --out DIR

Consume lo que recoge `crawl_setlist_browser --what conciertos` y saca los agregados
que sí se pueden publicar. No republica su índice: cuenta sobre él.

Tres cautelas que vienen de cómo escribe setlist.fm los lugares:

  · **El recinto y la ciudad llegan en el mismo texto** («at Palau Sant Jordi,
    Barcelona, Spain»), así que la última coma es el país y la penúltima la ciudad.
    Cuando solo hay dos piezas, no hay recinto y la primera ES la ciudad: tratar la
    primera como recinto siempre inventaría recintos con nombre de ciudad.
  · **Un festival no es una ciudad.** «Viña Rock», «Festimad» o «Azkena Rock» salen
    donde debería ir el recinto y a veces se comen la ciudad entera. Se marcan en vez
    de colarlos en el ranking de ciudades.
  · **La misma ciudad se escribe de varias formas** («A Coruña» / «La Coruña»,
    «Alicante» / «Alacant»). Se normalizan las que se han visto; lo que no se
    reconoce se cuenta aparte y se dice, nunca se fuerza a la más parecida.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

# Formas alternativas vistas en los datos → forma canónica.
ALIAS_CIUDAD = {
    "la coruna": "A Coruña", "a coruna": "A Coruña",
    "alacant": "Alicante", "donostia": "San Sebastián",
    "san sebastian": "San Sebastián", "donostia-san sebastian": "San Sebastián",
    "vitoria": "Vitoria-Gasteiz", "gasteiz": "Vitoria-Gasteiz",
    "vitoria-gasteiz": "Vitoria-Gasteiz",
    "palma de mallorca": "Palma", "palma": "Palma",
    "bilbo": "Bilbao", "iruna": "Pamplona", "pamplona-iruna": "Pamplona",
    "lleida": "Lleida", "lerida": "Lleida",
    "girona": "Girona", "gerona": "Girona",
    "castello de la plana": "Castellón", "castellon de la plana": "Castellón",
}
# Lo que aparece en el hueco del recinto pero es un festival, no un recinto fijo.
FESTIVALES = ("festival", "fest", "viña rock", "vina rock", "festimad", "azkena",
              "sonorama", "resurrection", "rock in rio", "derrame", "bbk")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower().strip())
    return "".join(c for c in s if not unicodedata.combining(c))


def canon_ciudad(c: str | None) -> str | None:
    if not c:
        return None
    return ALIAS_CIUDAD.get(_norm(c), c.strip())


def es_festival(recinto: str | None) -> bool:
    n = _norm(recinto)
    return bool(n) and any(f in n for f in FESTIVALES)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--browser", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    d = json.loads(Path(args.browser).read_text(encoding="utf-8"))
    todos: list[dict] = []
    for slug, a in d["artistas"].items():
        for c in a.get("conciertos", []):
            todos.append({**c, "artista": slug, "ciudad": canon_ciudad(c.get("ciudad"))})

    if not todos:
        print("sin conciertos en el fichero: ¿se corrió con --what conciertos?", file=sys.stderr)
        return 1

    sin_ciudad = [c for c in todos if not c["ciudad"]]
    ciudades = Counter(c["ciudad"] for c in todos if c["ciudad"])
    paises = Counter(c["pais"] for c in todos if c.get("pais"))
    recintos = Counter(c["recinto"] for c in todos
                       if c.get("recinto") and not es_festival(c["recinto"]))
    fests = Counter(c["recinto"] for c in todos if es_festival(c.get("recinto")))

    por_artista_ciudad: dict[str, Counter] = defaultdict(Counter)
    for c in todos:
        if c["ciudad"]:
            por_artista_ciudad[c["artista"]][c["ciudad"]] += 1

    # Ciudades de un solo concierto: la cola larga, que es un insight por sí misma.
    una_vez = [c for c, n in ciudades.items() if n == 1]

    payload = {
        "conciertos": len(todos),
        "cobertura": {
            "con_fecha": sum(1 for c in todos if c.get("fecha")),
            "con_ciudad": len(todos) - len(sin_ciudad),
            "con_recinto": sum(1 for c in todos if c.get("recinto")),
            "sin_ciudad": len(sin_ciudad),
        },
        "ciudades_distintas": len(ciudades),
        "ciudades_top": ciudades.most_common(30),
        "ciudades_una_vez": sorted(una_vez),
        "paises": paises.most_common(),
        "recintos_top": recintos.most_common(20),
        "festivales_top": fests.most_common(15),
        "por_artista": {k: v.most_common(15) for k, v in por_artista_ciudad.items()},
    }
    (out / "geografia.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    with (out / "conciertos.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["artista", "fecha", "ciudad", "recinto", "pais"])
        w.writeheader()
        for c in sorted(todos, key=lambda x: (x.get("fecha") or "")):
            w.writerow({k: c.get(k) for k in w.fieldnames})

    print(f"\nCONCIERTOS        {len(todos)}")
    print(f"  con fecha       {payload['cobertura']['con_fecha']}")
    print(f"  con ciudad      {payload['cobertura']['con_ciudad']}")
    print(f"  con recinto     {payload['cobertura']['con_recinto']}")
    print(f"CIUDADES          {len(ciudades)} distintas · {len(una_vez)} con un solo concierto")
    print(f"PAÍSES            {len(paises)}: {', '.join(f'{p} ({n})' for p, n in paises.most_common(8))}")
    print("\nTOP CIUDADES")
    for c, n in ciudades.most_common(15):
        print(f"  {n:>3}  {c}")
    print("\nTOP RECINTOS (sin festivales)")
    for r, n in recintos.most_common(10):
        print(f"  {n:>3}  {r}")
    if fests:
        print("\nFESTIVALES")
        for r, n in fests.most_common(8):
            print(f"  {n:>3}  {r}")
    if sin_ciudad:
        print(f"\n⚠ {len(sin_ciudad)} conciertos sin ciudad reconocida. Muestra:")
        for c in sin_ciudad[:5]:
            print(f"     {c.get('fecha') or '—'}  «{(c.get('literal') or '')[:90]}»")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
