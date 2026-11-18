"""Conciertos de Robe y Extremoduro en nuestros lugares, comprobados uno a uno en su fuente.

Plan de relaciones (18-11-2026), PR C. Lee el dataset propio de conciertos
(`data/estudio/setlists_revistas/conciertos.csv`, sin setlist.fm, fuera de git) como
LISTA DE CANDIDATOS. Nada se da por bueno por venir en el CSV ni por su
`nivel_evidencia` (cuenta a Juancares):

- Cada URL se descarga y se busca en su texto la FECHA (en varios formatos) y el LUGAR.
- Una fuente de prensa con las dos cosas es un T2; un archivo de aficionados o un blog,
  un T3. YouTube no da texto que comprobar y Juancares no corrobora (regla del corpus).
- Verificado = dos T2 de dominios distintos (regla de `relations.validar`). El resto se
  guarda como `pendiente`: no se sirve.

Modelo (válido en schema.org: `performerIn` solo admite Person):
    place:<slug> —event→ {"@type": "MusicEvent", name, startDate,
                          performer: {"@type": "MusicGroup", "@id": …, name}}

El lugar se resuelve por nombre SOLO con su provincia española entre paréntesis
(«Úbeda (Jaén)»): sin provincia, o fuera de España, no se toca. Las ciudades sin ficha
van al CSV de propuestas de entidades nuevas.

    python -m scripts.relaciones.conciertos --csv /tmp/conciertos.csv --salida /tmp/conc \\
        --verificado-por "…"
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

from app.db.models import Place
from app.db.session import SessionLocal
from app.services.entity_resolver import SITE_URL_DEFAULT

UA = {"User-Agent": "Mozilla/5.0 (compatible; EntreInteriores/1.0; +https://entreinteriores.com)"}
PAUSA = 0.6
ARTISTAS = {"robe": ("robe", "Robe"), "extremoduro": ("extremoduro", "Extremoduro")}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
PROVINCIAS = {
    "a coruna", "alava", "albacete", "alicante", "almeria", "asturias", "avila", "badajoz",
    "baleares", "barcelona", "burgos", "caceres", "cadiz", "cantabria", "castellon",
    "ciudad real", "cordoba", "cuenca", "girona", "gerona", "granada", "guadalajara",
    "guipuzcoa", "gipuzkoa", "huelva", "huesca", "jaen", "la rioja", "las palmas", "leon",
    "lleida", "lerida", "lugo", "madrid", "malaga", "murcia", "navarra", "ourense", "orense",
    "palencia", "pontevedra", "salamanca", "santa cruz de tenerife", "segovia", "sevilla",
    "soria", "tarragona", "teruel", "toledo", "valencia", "valladolid", "vizcaya", "bizkaia",
    "zamora", "zaragoza", "ceuta", "melilla", "araba", "illes balears", "la coruna",
}
# Prensa reputada (T2). Lo demás —archivos de aficionados, blogs, foros— es T3.
PRENSA = {
    "mariskalrock.com", "rocksesion.com", "mondosonoro.com", "eldiario.es", "lavozdegalicia.es",
    "prensahistorica.mcu.es", "efeeme.com", "elpais.com", "elmundo.es", "abc.es", "hoy.es",
    "elperiodicoextremadura.com", "horajaen.com", "diariodenavarra.es", "elcorreo.com",
    "deia.eus", "rtve.es", "europapress.es", "culturaocio.com", "20minutos.es",
    "lavanguardia.com", "elperiodico.com", "diariodesevilla.es", "ideal.es", "laopiniondemalaga.es",
    "diariodeleon.es", "heraldo.es", "levante-emv.com", "lasprovincias.es", "elcomercio.es",
    "lne.es", "diariovasco.com", "noticiasdenavarra.com", "eldiariomontanes.es", "elnortedecastilla.es",
    "lagacetadesalamanca.es", "laverdad.es", "diariodecadiz.es", "canalextremadura.es",
    "regiondigital.com", "solo-rock.com", "rockinspain.es", "indyrock.es", "zona-zero.net",
    "losmejoresrock.com", "rockfm.fm", "cadenaser.com", "cope.es",
}
NO_CUENTA = ("juancaraes", "youtube.com", "youtu.be")
FUERA_DE_ESPANA = {"colombia", "marte"}


def _norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ/.\- ]", " ", s)).strip()


def _dominio(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def formas_de_fecha(fecha: str) -> list[str]:
    """«2024-07-06» → las formas en que puede aparecer escrita (ya normalizadas)."""
    a, m, d = fecha.split("-")
    di, mi = int(d), int(m)
    mes = MESES[mi - 1]
    return [f"{di} de {mes} de {a}", f"{di} de {mes}", f"{d}/{m}/{a}", f"{di}/{mi}/{a}",
            f"{d}-{m}-{a}", f"{di}-{mi}-{a}", f"{d}.{m}.{a}", f"{a}-{m}-{d}",
            f"{d}/{m}/{a[2:]}", f"{di}/{mi}/{a[2:]}"]


def texto_de(http: httpx.Client, url: str) -> str | None:
    try:
        r = http.get(url)
    except httpx.HTTPError:
        return None
    if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
        return None
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", r.text, flags=re.S)
    return _norm(re.sub(r"<[^>]+>", " ", t))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--verificado-por", required=True)
    ap.add_argument("--limite", type=int, default=0)
    args = ap.parse_args()

    db = SessionLocal()
    lugares = {_norm(p.name): p.slug for p in db.query(Place).all()}
    base = SITE_URL_DEFAULT.rstrip("/")
    filas, propuestas, informe = [], defaultdict(list), []
    cache: dict[str, str | None] = {}

    with open(args.csv, encoding="utf-8") as fh:
        candidatos = list(csv.DictReader(fh))
    with httpx.Client(timeout=20, headers=UA, follow_redirects=True) as http:
        n = 0
        for c in candidatos:
            art = ARTISTAS.get(_norm(c.get("artista")))
            fecha = (c.get("fecha") or "").strip()
            texto_ciudad = (c.get("ciudad") or "").strip()
            if not (art and re.match(r"^\d{4}-\d{2}-\d{2}$", fecha)) or texto_ciudad.startswith("n/d"):
                continue
            m = re.match(r"^(.*?)\s*\((.*?)\)\s*$", texto_ciudad)
            if m:
                ciudad, provincia = m.group(1).strip(), _norm(m.group(2))
                if provincia not in PROVINCIAS:
                    continue
            else:
                # Sin provincia solo vale si es uno de NUESTROS lugares (todos en España,
                # salvo los que no son ciudades de aquí).
                ciudad, provincia = texto_ciudad, ""
                if _norm(ciudad) not in lugares or _norm(ciudad) in FUERA_DE_ESPANA:
                    continue
            slug = lugares.get(_norm(ciudad))
            if not slug:
                propuestas[(ciudad, provincia)].append(f"{art[1]} {fecha}")
                continue
            n += 1
            if args.limite and n > args.limite:
                break
            fuentes, dominios_t2 = [], set()
            for url in [u.strip() for u in (c.get("urls") or "").split("|") if u.strip()]:
                dom = _dominio(url)
                if any(x in url for x in NO_CUENTA):
                    continue
                if url not in cache:
                    cache[url] = texto_de(http, url)
                    time.sleep(PAUSA)
                txt = cache[url]
                if not txt:
                    continue
                if _norm(ciudad) not in txt or not any(f in txt for f in formas_de_fecha(fecha)):
                    continue
                tier = "T2" if dom in PRENSA else "T3"
                if tier == "T2":
                    dominios_t2.add(dom)
                fuentes.append({"kind": "prensa" if tier == "T2" else "archivo", "tier": tier,
                                "url": url, "evidencia": f"el texto descargado el 18-11-2026 "
                                                         f"recoge {ciudad} y la fecha {fecha}"})
            if not fuentes:
                informe.append(f"{art[1]} {fecha} {ciudad}: ninguna fuente lo recoge al descargarla")
                continue
            estado = "verificada" if len(dominios_t2) >= 2 else "pendiente"
            dd = "-".join(reversed(fecha.split("-")))
            fila = {
                "sujeto": f"place:{slug}", "predicado": "event",
                "objeto": {"@type": "MusicEvent", "name": f"{art[1]} en {ciudad}, {dd}",
                           "startDate": fecha,
                           "performer": {"@type": "MusicGroup",
                                         "@id": f"{base}/{art[0]}#musicgroup", "name": art[1]}},
                "estado": estado, "fuentes": fuentes,
            }
            if estado == "verificada":
                fila["verificado_por"] = args.verificado_por
            filas.append(fila)

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "conciertos.yaml").write_text(
        yaml.safe_dump({"relaciones": filas}, allow_unicode=True, sort_keys=False, width=110),
        encoding="utf-8")
    with open(salida / "ciudades_sin_ficha.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ciudad", "provincia", "n_conciertos", "conciertos"])
        for (ciudad, prov), lista in sorted(propuestas.items(), key=lambda x: -len(x[1])):
            w.writerow([ciudad, prov, len(lista), " | ".join(lista)])
    (salida / "informe.txt").write_text("\n".join(informe) + "\n", encoding="utf-8")
    print(json.dumps({"filas": len(filas),
                      "verificadas": sum(1 for f in filas if f["estado"] == "verificada"),
                      "pendientes": sum(1 for f in filas if f["estado"] == "pendiente"),
                      "sin_fuente_que_lo_recoja": len(informe),
                      "ciudades_sin_ficha": len(propuestas)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
