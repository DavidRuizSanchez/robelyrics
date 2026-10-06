"""Descarga las páginas públicas de estadísticas de setlist.fm y las parsea.

    python -m scripts.pr.fetch_setlist_index --out /ruta/fuera/del/repo
    python -m scripts.pr.fetch_setlist_index --out ... --raw-dir ...   # guarda el HTML

Qué hace y qué NO hace, porque aquí lo importante es lo segundo:

  · NO escribe en la base de datos. El dato de setlist.fm no entra en nuestro
    catálogo: se usa para calcular agregados e índices derivados y se cita.
  · NO republica su tabla. Lo que sale es su JSON intermedio para el estudio;
    lo publicable son los agregados que calcula `build_study_dataset`.
  · NO lleva nada de evasión antibot. Si el WAF corta, el script lo dice y
    termina con error. Ver abajo.
  · Espera `PAUSA` segundos entre peticiones, que es el límite que piden sus
    propios términos («not more than once during any three-second interval»).

ATRIBUCIÓN: sus términos exigen mostrar atribución allí donde se use el dato y
**prohíben el `nofollow`** en el enlace de vuelta. Eso viaja en el manifiesto
para que el entregable no se publique sin ella.

LO QUE SE PUEDE Y LO QUE NO (medido el 06-10-2026)
--------------------------------------------------
Las URLs SIN parámetros se descargan bien. Las que llevan query string
(`?year=1996`, `?tour=33d6706d`) devuelven **HTTP 202 con 0 bytes**: es el WAF
de AWS (la página carga `awswaf.com/.../jsapi.js`). Y tras unas pocas
peticiones automatizadas seguidas, el WAF empieza a devolver 202 también en la
página base. Pasarlo requeriría un navegador real, que es justo lo que este
proyecto no hace.

La buena noticia es que no hace falta: la serie COMPLETA de años y de giras ya
viene en el HTML de la página sin parámetros (el «Show all» solo despliega lo
que ya está). Verificado: los 17 años de Extremoduro suman 459, que es su total
de setlists, y los 4 de Robe suman 132.

Lo que NO se obtiene por esta vía, y por tanto no se puede afirmar en el
estudio: ciudades y recintos (están concierto a concierto, 46 páginas
paginadas) y la primera/última vez que sonó cada canción (una página por
canción). Si algún día se necesitan, se piden a setlist.fm, no se fuerzan.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import httpx

from scripts.pr.setlist_parse import parse_artista, parse_discos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE = "https://www.setlist.fm"
# Su propio límite: «not more than once during any three-second interval».
PAUSA = 3.5

ATRIBUCION = {
    "fuente": "setlist.fm",
    "url": f"{BASE}",
    "exige_atribucion_visible": True,
    "prohibe_nofollow": True,
    "nota": (
        "Sus términos exigen atribución visible donde se use el dato y prohíben "
        "marcar el enlace de vuelta con nofollow. El estudio publica agregados "
        "e índices derivados propios, no su tabla."
    ),
}

# (slug nuestro, id de setlist.fm). El id va en la URL y es estable.
ARTISTAS = (
    ("extremoduro", "extremoduro-13d68da1"),
    ("robe", "robe-63c74607"),
)


class WafCortado(RuntimeError):
    """El WAF ha respondido 202/403. No se insiste y no se escribe nada."""


def _descargar(client: httpx.Client, ruta: str) -> tuple[str, dict]:
    url = f"{BASE}/{ruta}"
    r = client.get(url)
    cuerpo = r.text
    sello = {
        "url": url,
        "http_status": r.status_code,
        "bytes": len(r.content),
        "sha256": hashlib.sha256(r.content).hexdigest(),
        "consultado_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    # 202 con cuerpo vacío es la firma del WAF. Tratarlo como éxito es el fallo
    # que ya nos pasó con el token de GSC: el job escribía `pages: {}` con exit
    # 0 y se publicaba el vacío. Aquí se corta en seco.
    if r.status_code != 200 or len(r.content) < 10_000:
        raise WafCortado(
            f"{url} → HTTP {r.status_code}, {len(r.content)} bytes. "
            "Es el WAF de setlist.fm. No se reintenta ni se disfraza el cliente: "
            "espera un rato y vuelve a lanzarlo, o pide acceso a setlist.fm."
        )
    return cuerpo, sello


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="directorio de salida (FUERA del repo)")
    ap.add_argument("--raw-dir", help="si se pasa, guarda el HTML crudo descargado")
    ap.add_argument(
        "--from-raw",
        help="no descarga nada: parsea el HTML ya guardado en este directorio",
    )
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    raw_dir = Path(args.raw_dir) if args.raw_dir else None
    if raw_dir:
        raw_dir.mkdir(parents=True, exist_ok=True)

    paginas: dict[str, str] = {}
    manifiesto: list[dict] = []

    if args.from_raw:
        origen = Path(args.from_raw)
        for slug, sid in ARTISTAS:
            # La URL se emparejó mal en la primera versión: anotaba la de
            # estadísticas para las dos páginas, así que el ledger decía que la
            # tabla de discos venía de la página de canciones. Un ledger con la
            # fuente equivocada es peor que no tenerlo.
            for clave, fichero, ruta in (
                (f"{slug}_stats", f"{slug}_stats.html", f"stats/{sid}.html"),
                (f"{slug}_albums", f"albums_{slug}.html", f"stats/albums/{sid}.html"),
            ):
                p = origen / fichero
                if not p.exists():
                    logger.error("falta %s", p)
                    return 1
                paginas[clave] = p.read_text(encoding="utf-8", errors="replace")
                manifiesto.append(
                    {
                        "url": f"{BASE}/{ruta}",
                        "origen": "html guardado",
                        "fichero": str(p),
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                )
    else:
        cabeceras = {
            # Nos identificamos. Si esto no pasa el WAF, la respuesta es pedir
            # acceso, no fingir ser Chrome.
            "User-Agent": "RobeLyrics/1.0 (+https://entreinteriores.com; davidruizsanchez@gmail.com)",
            "Accept-Language": "es-ES,es;q=0.9",
        }
        with httpx.Client(headers=cabeceras, timeout=30.0, follow_redirects=True) as client:
            primera = True
            for slug, sid in ARTISTAS:
                for clave, ruta in (
                    (f"{slug}_stats", f"stats/{sid}.html"),
                    (f"{slug}_albums", f"stats/albums/{sid}.html"),
                ):
                    if not primera:
                        time.sleep(PAUSA)
                    primera = False
                    try:
                        cuerpo, sello = _descargar(client, ruta)
                    except WafCortado as e:
                        logger.error("%s", e)
                        return 2
                    paginas[clave] = cuerpo
                    manifiesto.append(sello)
                    logger.info("ok %s (%s bytes)", ruta, sello["bytes"])
                    if raw_dir:
                        (raw_dir / f"{clave}.html").write_text(cuerpo, encoding="utf-8")

    # ---- parseo y validación cruzada ----
    datos: dict[str, dict] = {}
    for slug, _sid in ARTISTAS:
        art = parse_artista(paginas[f"{slug}_stats"], slug)
        discos = parse_discos(paginas[f"{slug}_albums"])

        if not art.canciones or not discos:
            logger.error("%s: parseo vacío. No se escribe nada.", slug)
            return 1
        # Dos tablas de páginas distintas tienen que dar el mismo total. Es la
        # única prueba de que no se han caído filas por el camino.
        if not art.cuadra_con_discos(discos):
            logger.error(
                "%s: las canciones suman %d y los discos %d. La extracción se ha "
                "dejado filas: NO se escribe nada.",
                slug, art.toques_totales, sum(n for _, n in discos),
            )
            return 1

        datos[slug] = {
            **asdict(art),
            "canciones": [asdict(c) for c in art.canciones],
            "discos": [{"bloque": n, "toques": c} for n, c in discos],
            "anyos_completos": art.anyos_completos,
            "giras_completas": art.giras_completas,
            "toques_totales": art.toques_totales,
        }
        logger.info(
            "%s: %s setlists · %d canciones · %d toques · años completos=%s · giras completas=%s",
            slug, art.setlists, len(art.canciones), art.toques_totales,
            art.anyos_completos, art.giras_completas,
        )

    payload = {
        "generado_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "atribucion": ATRIBUCION,
        "manifiesto": manifiesto,
        "limitaciones": [
            "Ciudades y recintos NO disponibles por esta vía (viven concierto a concierto).",
            "Primera/última vez que sonó cada canción NO disponible (una página por canción).",
            "Los desgloses por gira de setlist.fm son poco fiables: la página de «Agila 96» "
            "declara 53 conciertos y su canción más tocada sale con 4 toques. No usarlos "
            "para series temporales; los totales por artista y por disco sí cuadran.",
        ],
        "artistas": datos,
    }
    destino = out / "setlist_stats.json"
    destino.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("escrito %s", destino)
    return 0


if __name__ == "__main__":
    sys.exit(main())
