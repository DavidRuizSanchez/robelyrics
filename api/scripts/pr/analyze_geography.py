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
    # setlist.fm escribe algunas ciudades españolas con su EXÓNIMO INGLÉS. Salen
    # mezcladas con las demás y rompen el ranking: «Seville» con 12 conciertos
    # convivía con «Sevilla» como si fueran dos sitios.
    "seville": "Sevilla", "saragossa": "Zaragoza", "cordova": "Córdoba",
    "corunna": "A Coruña", "majorca": "Palma", "catalonia": "Cataluña",
    "andalusia": "Andalucía", "biscay": "Vizcaya", "navarre": "Navarra",
    "basque country": "País Vasco",
}
# Lo que aparece en el hueco del recinto pero es un festival, no un recinto fijo.
# «fest» a secas cazaba «Casal de Festes», que es una sala: por eso van tokens
# completos y no subcadenas sueltas.
FESTIVALES = ("festival", "viña rock", "vina rock", "festimad", "azkena", "sonorama",
              "resurrection", "rock in rio", "derrame", "bbk", "rockout", "esparrago",
              "san fermin", "shikillo", "doctor music", "viñarock")

# setlist.fm usa este literal cuando nadie sabe dónde fue. No es un recinto y
# encabezaba el ranking con 31 conciertos.
PLACEHOLDER_RECINTO = {"unknown venue", "unknown", ""}

# Nombres de recinto que NO identifican un sitio: cada ciudad tiene el suyo.
# «Plaza de Toros» sumaba 16 conciertos de dieciséis plazas distintas, y «Campo
# de Futbol» y «Campo de fútbol» se contaban por separado por la tilde. Estos se
# cualifican con la ciudad; el resto se deja tal cual.
GENERICOS_RECINTO = {
    "plaza de toros", "campo de futbol", "campo de deportes", "auditorio municipal",
    "recinto ferial", "recinto hipico", "polideportivo", "polideportivo municipal",
    "pabellon municipal", "pabellon municipal de deportes", "pabellon de deportes",
    "palacio de deportes", "palacio de los deportes", "plaza de la constitucion",
    "plaza mayor", "estadio municipal", "parque municipal", "sala municipal",
    "carpa", "pabellon polideportivo",
}



# --------------------------------------------------------------------------- #
# Provincias
# --------------------------------------------------------------------------- #
# El ranking por ciudad reparte lo que en realidad está junto: Madrid aparece con
# 34 conciertos y su área con otros 10 en Leganés, Rivas, Alcalá, Pozuelo y
# Móstoles. La provincia junta eso sin inventarse nada, y es además el corte que
# le interesa a la prensa regional.
#
# El mapa se escribe a mano porque no hay fuente de la que derivarlo aquí. Lo que
# no esté, NO se adivina: se cuenta aparte y se declara la cobertura.
PROVINCIA: dict[str, str] = {
    # capitales y cabeceras
    "Madrid": "Madrid", "Barcelona": "Barcelona", "Cáceres": "Cáceres",
    "Zaragoza": "Zaragoza", "Valladolid": "Valladolid", "A Coruña": "A Coruña",
    "Sevilla": "Sevilla", "Valencia": "Valencia", "Bilbao": "Vizcaya",
    "Granada": "Granada", "Plasencia": "Cáceres", "Logroño": "La Rioja",
    "Vitoria-Gasteiz": "Álava", "Málaga": "Málaga", "Pamplona": "Navarra",
    "Alicante": "Alicante", "Gijón": "Asturias", "Murcia": "Murcia",
    "Palma": "Baleares", "Vigo": "Pontevedra", "Albacete": "Albacete",
    "Las Palmas de Gran Canaria": "Las Palmas", "Salamanca": "Salamanca",
    "San Sebastián": "Guipúzcoa", "Almería": "Almería", "Burgos": "Burgos",
    "Cuenca": "Cuenca", "Cádiz": "Cádiz", "Leganés": "Madrid", "León": "León",
    "Daimiel": "Ciudad Real", "Santiago de Compostela": "A Coruña",
    "Toledo": "Toledo", "Badajoz": "Badajoz", "Badalona": "Barcelona",
    "Girona": "Girona", "Jaén": "Jaén", "Mérida": "Badajoz",
    "Santander": "Cantabria", "Vila-real": "Castellón",
    "Alcalá de Henares": "Madrid", "Alcázar de San Juan": "Ciudad Real",
    "Avilés": "Asturias", "Hervás": "Cáceres", "Lleida": "Lleida",
    "Onda": "Castellón", "Ponferrada": "León", "Pontevedra": "Pontevedra",
    "Rivas-Vaciamadrid": "Madrid", "San Cristóbal de La Laguna": "Santa Cruz de Tenerife",
    "Sant Feliu de Guíxols": "Girona", "Segovia": "Segovia", "Soria": "Soria",
    "Tarragona": "Tarragona", "Villarrobledo": "Albacete", "Villena": "Alicante",
    "Zamora": "Zamora", "Alcantarilla": "Murcia", "Almassora": "Castellón",
    "Aranda de Duero": "Burgos", "Armilla": "Granada", "Barakaldo": "Vizcaya",
    "Beniparrell": "Valencia", "Binéfar": "Huesca", "Briviesca": "Burgos",
    "Castelldefels": "Barcelona", "Churra": "Murcia", "Guadalajara": "Guadalajara",
    "Huelva": "Huelva", "Huesca": "Huesca", "Irun": "Guipúzcoa",
    "Jerez de la Frontera": "Cádiz", "Lugo": "Lugo", "Melgar de Fernamental": "Burgos",
    "Ourense": "Ourense", "Puente la Reina": "Navarra", "Reus": "Tarragona",
    "Salt": "Girona", "Santa Cruz de Tenerife": "Santa Cruz de Tenerife",
    "Talavera de la Reina": "Toledo", "Terrassa": "Barcelona",
    "Torrelavega": "Cantabria", "Yecla": "Murcia", "Úbeda": "Jaén",
    # una sola vez
    "Albal": "Valencia", "Albalat de la Ribera": "Valencia", "Albatera": "Alicante",
    "Alcañiz": "Teruel", "Alcuéscar": "Cáceres", "Alfaro": "La Rioja",
    "Alhendín": "Granada", "Aliseda": "Cáceres", "Almansa": "Albacete",
    "Almazán": "Soria", "Almendralejo": "Badajoz", "Arrasate/Mondragón": "Guipúzcoa",
    "Arrecife": "Las Palmas", "Balmaseda": "Vizcaya", "Benidorm": "Alicante",
    "Berango": "Vizcaya", "Bergara": "Guipúzcoa", "Bezana": "Cantabria",
    "Cabanillas del Campo": "Guadalajara", "Cabezuela": "Cáceres",
    "Candeleda": "Ávila", "Cartagena": "Murcia", "Castellón": "Castellón",
    "Catral": "Alicante", "Cenicero": "La Rioja", "Cerdanyola del Vallès": "Barcelona",
    "Chipiona": "Cádiz", "Chirivel": "Almería", "Cieza": "Murcia",
    "Ciudad Real": "Ciudad Real", "Coín": "Málaga", "Córdoba": "Córdoba",
    "Deba": "Guipúzcoa", "Don Benito": "Badajoz", "Dos Hermanas": "Sevilla",
    "Elda": "Alicante", "Empuriabrava": "Girona", "Estella": "Navarra",
    "Ferrol": "A Coruña", "Forcall": "Castellón", "Fraga": "Huesca",
    "Gandia": "Valencia", "Grado": "Asturias", "Granollers": "Barcelona",
    "Guernica": "Vizcaya", "Gáldar": "Las Palmas", "Hernani": "Guipúzcoa",
    "Illescas": "Toledo", "L'Hospitalet de Llobregat": "Barcelona",
    "La Rábida": "Huelva", "La Selva del Camp": "Tarragona", "Laredo": "Cantabria",
    "Lesaka": "Navarra", "Llutxent": "Valencia", "Los Alcázares": "Murcia",
    "Madroñera": "Cáceres", "Mairena del Aljarafe": "Sevilla", "Mallorca": "Baleares",
    "Malpartida de Cáceres": "Cáceres", "Manlleu": "Barcelona", "Maracena": "Granada",
    "Miajadas": "Cáceres", "Molina de Segura": "Murcia",
    "Montalbán de Córdoba": "Córdoba", "Motril": "Granada", "Muchamiel": "Alicante",
    "Móstoles": "Madrid", "Narón": "A Coruña", "Oia": "Pontevedra",
    "Ontinyent": "Valencia", "Oviedo": "Asturias", "Paiporta": "Valencia",
    "Palencia": "Palencia", "Pedreguer": "Alicante", "Porreres": "Baleares",
    "Pozoblanco": "Córdoba", "Pozuelo de Alarcón": "Madrid", "Pradejón": "La Rioja",
    "Quart de Poblet": "Valencia", "Quintanilla de Somoza": "León", "Rafal": "Alicante",
    "Recas": "Toledo", "Ronda": "Málaga", "Salou": "Tarragona",
    "San Bartolomé": "Las Palmas", "San Fernando": "Cádiz", "San Javier": "Murcia",
    "Sanlúcar de Barrameda": "Cádiz", "Sant Andreu de la Barca": "Barcelona",
    "Santa Coloma de Gramenet": "Barcelona", "Santoña": "Cantabria",
    "Sarón": "Cantabria", "Teruel": "Teruel", "Torre-Pacheco": "Murcia",
    "Torredembarra": "Tarragona", "Tàrrega": "Lleida", "Valdastillas": "Cáceres",
    "Valverde del Fresno": "Cáceres", "Villafranca de los Barros": "Badajoz",
    "Villamartín": "Cádiz", "Xirivella": "Valencia", "Ávila": "Ávila",
}

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower().strip())
    return "".join(c for c in s if not unicodedata.combining(c))


def canon_ciudad(c: str | None, pais: str | None = None) -> str | None:
    """Forma canónica de la ciudad. `pais` desambigua los homónimos.

    Hace falta por «Santiago»: una es Santiago de Chile (Teatro La Cúpula, 2012) y
    la otra Santiago de Compostela (Pabellón Multiusos, 2004, país España). Sin el
    país se cuentan juntas y Galicia pierde un concierto.
    """
    if not c:
        return None
    n = _norm(c)
    if n == "santiago" and _norm(pais) == "spain":
        return "Santiago de Compostela"
    return ALIAS_CIUDAD.get(n, c.strip())


def es_festival(recinto: str | None) -> bool:
    n = _norm(recinto)
    return bool(n) and any(f in n for f in FESTIVALES)


def canon_recinto(recinto: str | None, ciudad: str | None) -> str | None:
    """Nombre de recinto utilizable, o None si no identifica ningún sitio.

    Devuelve «Nombre (Ciudad)» cuando el nombre es genérico, porque sin la ciudad
    no se está contando un recinto sino una categoría de recinto.
    """
    if not recinto:
        return None
    n = _norm(recinto)
    if n in PLACEHOLDER_RECINTO:
        return None
    if n in GENERICOS_RECINTO:
        return f"{recinto.strip()} ({ciudad})" if ciudad else None
    return recinto.strip()


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
            todos.append({**c, "artista": slug, "ciudad": canon_ciudad(c.get("ciudad"), c.get("pais"))})

    if not todos:
        print("sin conciertos en el fichero: ¿se corrió con --what conciertos?", file=sys.stderr)
        return 1

    sin_ciudad = [c for c in todos if not c["ciudad"]]
    ciudades = Counter(c["ciudad"] for c in todos if c["ciudad"])
    paises = Counter(c["pais"] for c in todos if c.get("pais"))
    recintos = Counter()
    for c in todos:
        if es_festival(c.get("recinto")):
            continue
        r = canon_recinto(c.get("recinto"), c.get("ciudad"))
        if r:
            recintos[r] += 1
    sin_recinto_util = sum(
        1 for c in todos
        if not es_festival(c.get("recinto")) and not canon_recinto(c.get("recinto"), c.get("ciudad"))
    )
    fests = Counter(c["recinto"] for c in todos if es_festival(c.get("recinto")))

    por_artista_ciudad: dict[str, Counter] = defaultdict(Counter)
    for c in todos:
        if c["ciudad"]:
            por_artista_ciudad[c["artista"]][c["ciudad"]] += 1

    # Ciudades de un solo concierto: la cola larga, que es un insight por sí misma.
    una_vez = [c for c, n in ciudades.items() if n == 1]

    # Provincias. Solo cuentan los conciertos en España: la provincia no aplica
    # fuera, y meterlos en un «sin asignar» ensuciaría la cobertura.
    provincias: Counter = Counter()
    ciudades_sin_provincia: set = set()
    for c in todos:
        if _norm(c.get("pais")) not in ("spain", ""):
            continue
        ciu = c["ciudad"]
        if not ciu:
            continue
        prov = PROVINCIA.get(ciu)
        if prov:
            provincias[prov] += 1
        else:
            ciudades_sin_provincia.add(ciu)

    payload = {
        "conciertos": len(todos),
        "cobertura": {
            "con_fecha": sum(1 for c in todos if c.get("fecha")),
            "con_ciudad": len(todos) - len(sin_ciudad),
            "con_recinto": sum(1 for c in todos if c.get("recinto")),
            "sin_ciudad": len(sin_ciudad),
            "sin_recinto_identificable": sin_recinto_util,
        },
        "ciudades_distintas": len(ciudades),
        "ciudades_top": ciudades.most_common(30),
        "ciudades_una_vez": sorted(una_vez),
        "paises": paises.most_common(),
        "provincias": provincias.most_common(),
        "provincias_distintas": len(provincias),
        "conciertos_con_provincia": sum(provincias.values()),
        "ciudades_sin_provincia": sorted(ciudades_sin_provincia),
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
    print(f"  con recinto     {payload['cobertura']['con_recinto']}"
          f"  (sin recinto identificable: {sin_recinto_util})")
    print(f"CIUDADES          {len(ciudades)} distintas · {len(una_vez)} con un solo concierto")
    print(f"PAÍSES            {len(paises)}: {', '.join(f'{p} ({n})' for p, n in paises.most_common(8))}")
    print("\nTOP CIUDADES")
    for c, n in ciudades.most_common(15):
        print(f"  {n:>3}  {c}")
    print(f"\nPROVINCIAS       {len(provincias)} distintas · {sum(provincias.values())} conciertos asignados")
    for pr, n in provincias.most_common(15):
        print(f"  {n:>3}  {pr}")
    if ciudades_sin_provincia:
        print(f"  ⚠ {len(ciudades_sin_provincia)} ciudades sin provincia en el mapa: "
              f"{', '.join(sorted(ciudades_sin_provincia)[:8])}")

    print("\nTOP RECINTOS (sin festivales ni genéricos sin ciudad)")
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
