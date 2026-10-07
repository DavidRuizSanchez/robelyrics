"""Reparte el dato del estudio del repertorio por las páginas de la web.

    docker compose exec api python -m scripts.pr.build_page_data \
        --setlist /tmp/estudio/setlist_stats.json \
        --conciertos /tmp/estudio_ciudades/conciertos.csv \
        --out /tmp/datos-por-pagina.ts

y luego se copia el `.ts` a `web/components/estudio/datos-por-pagina.ts`.

Por qué un fichero del frontend y no `seo_content.body_md`: el dato de directo es
de setlist.fm y la decisión es que **no entra en nuestra BD**. Además así hay una
sola fuente de verdad: si se regenera el estudio, se regenera esto y ninguna
cifra queda copiada a mano en el cuerpo de una ficha.

Reutiliza el casado de `build_study_dataset` (catálogo canónico + emparejado de
títulos), así que una ficha dice exactamente lo mismo que el estudio. Las cifras
de directo van EN BRUTO por formación, nunca normalizadas sobre los 459 setlists
de Extremoduro: la densidad de registro de 1987-2002 es diez veces menor que la
de 2008-2014 (ver `gotcha_setlistfm_terminos`).
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml
from sqlalchemy import select

from app.db.models import Album, Artist, Song
from app.db.session import SessionLocal
from app.services.kw_normalize import kw_norm
from scripts.pr.analyze_geography import PROVINCIA, canon_ciudad
from scripts.pr.build_study_dataset import NO_SON_DISCOS, catalogo, clave, emparejar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TAXONOMIES = Path(__file__).resolve().parents[2] / "data" / "taxonomies.yaml"
TAXONOMIES_APP = Path("/app/data/taxonomies.yaml")

# Fichas de `/lugares` que no son una ciudad: se agregan por provincia o por país.
REGIONES = {"extremadura": ("Cáceres", "Badajoz")}
PAISES = {"colombia": "Colombia"}


def _toques_por_composicion(setlist: dict, comps: dict) -> dict[str, dict[str, int]]:
    """Mismo cruce que `build_study_dataset.repertorio`, devuelto por clave nuestra."""
    toques: dict[str, dict[str, int]] = defaultdict(dict)
    for slug, a in setlist["artistas"].items():
        for c in a["canciones"]:
            toques[clave(c["titulo"])][slug] = c["toques"]
    mapa, _, _ = emparejar(comps, dict(toques))
    return {mapa[k]: v for k, v in toques.items() if k in mapa}


def _comp_de_cada_fila(db, comps: dict) -> dict[str, str]:
    """`path` de cada fila de `songs` → clave de su composición canónica.

    Las regrabaciones y los directos tienen ficha propia y son la misma
    composición: «Jesucristo García (Rock Transgresivo)» suena en directo lo
    mismo que la de 1990. Se resuelven una a una con el mismo emparejado.
    """
    filas = db.execute(
        select(Song.title, Song.slug, Album.slug, Artist.slug)
        .join(Album, Album.id == Song.album_id)
        .join(Artist, Artist.id == Album.artist_id)
    ).all()
    out: dict[str, str] = {}
    sueltas = []
    for titulo, song_slug, album_slug, artista in filas:
        path = f"/{artista}/{album_slug}/{song_slug}"
        k = clave(titulo)
        if k in comps:
            out[path] = k
        else:
            sueltas.append((path, k))
    for path, k in sueltas:
        mapa, _, _ = emparejar(comps, {k: 1})
        if k in mapa:
            out[path] = mapa[k]
        else:
            logger.warning("sin composición para %s («%s»): no se le pinta dato", path, k)
    return out


def _discos(db, setlist: dict, nunca: set[str], comps: dict) -> dict[str, dict]:
    """Bloques de la página de discos de setlist.fm → nuestras fichas de disco."""
    albums = db.execute(
        select(Album.title, Album.slug, Album.kind, Artist.slug)
        .join(Artist, Artist.id == Album.artist_id)
        .where(Album.kind.in_(("studio", "ep")))
    ).all()
    idx = {(artista, kw_norm(t)): f"/{artista}/{s}" for t, s, _, artista in albums}
    once_por_disco = Counter(
        f"/{comps[k]['artista']}/{comps[k]['album_slug']}" for k in nunca
    )
    out: dict[str, dict] = {}
    for artista, a in setlist["artistas"].items():
        total = sum(b["toques"] for b in a["discos"])
        for b in a["discos"]:
            if kw_norm(b["bloque"]) in NO_SON_DISCOS:
                continue
            path = idx.get((artista, kw_norm(b["bloque"])))
            if not path:
                logger.warning("bloque «%s» de %s sin ficha de disco", b["bloque"], artista)
                continue
            out[path] = {
                "toques": b["toques"],
                "pct": round(100.0 * b["toques"] / total, 1),
                "setlists": int(a["setlists"]),
                "once": once_por_disco.get(path, 0),
            }
    return out


def _geografia(conciertos_csv: Path, lugares: dict[str, str]) -> tuple[dict, dict]:
    filas = list(csv.DictReader(conciertos_csv.open(encoding="utf-8")))
    for f in filas:
        f["ciudad"] = canon_ciudad(f.get("ciudad"), f.get("pais"))
        f["provincia"] = PROVINCIA.get(f["ciudad"]) if f.get("pais") == "Spain" else None

    provincias = Counter(f["provincia"] for f in filas if f["provincia"])
    # El puesto solo se da cuando no hay empate: con 11 conciertos empatan Badajoz,
    # Málaga, Castellón y Albacete, y «la 20.ª» sería un artefacto del orden.
    veces = Counter(provincias.values())
    rank_prov = {
        p: i + 1 for i, (p, n) in enumerate(provincias.most_common()) if veces[n] == 1
    }
    primera_fecha = min(f["fecha"] for f in filas if f.get("fecha"))

    def resumen(sel: list[dict]) -> dict:
        fechas = sorted(f["fecha"] for f in sel if f.get("fecha"))
        primero = next(f for f in sorted(sel, key=lambda x: x.get("fecha") or "9999"))
        return {
            "n": len(sel),
            "extremoduro": sum(1 for f in sel if f["artista"] == "extremoduro"),
            "robe": sum(1 for f in sel if f["artista"] == "robe"),
            "primero": fechas[0] if fechas else None,
            "primero_recinto": primero.get("recinto") or None,
            "ultimo": fechas[-1] if fechas else None,
            "es_el_primero": bool(fechas) and fechas[0] == primera_fecha,
        }

    out_lugar: dict[str, dict] = {}
    for slug, nombre in lugares.items():
        if slug in REGIONES:
            sel = [f for f in filas if f["provincia"] in REGIONES[slug]]
            if sel:
                out_lugar[slug] = {
                    "tipo": "region", "nombre": nombre, **resumen(sel),
                    "provincias": {p: provincias[p] for p in REGIONES[slug]},
                    "ciudades": len({f["ciudad"] for f in sel}),
                }
            continue
        if slug in PAISES:
            sel = [f for f in filas if f.get("pais") == PAISES[slug]]
            if sel:
                out_lugar[slug] = {
                    "tipo": "pais", "nombre": nombre, **resumen(sel),
                    "ciudades": sorted({f["ciudad"] for f in sel if f["ciudad"]}),
                }
            continue
        sel = [f for f in filas if f["ciudad"] == nombre]
        if not sel:
            continue
        prov = sel[0]["provincia"]
        out_lugar[slug] = {
            "tipo": "ciudad", "nombre": nombre, **resumen(sel),
            "provincia": prov,
            "provincia_n": provincias.get(prov, 0) if prov else 0,
            "provincia_rank": rank_prov.get(prov) if prov else None,
        }

    out_artista: dict[str, dict] = {}
    for artista in ("extremoduro", "robe"):
        sel = [f for f in filas if f["artista"] == artista]
        out_artista[artista] = {
            "ciudades": len({f["ciudad"] for f in sel if f["ciudad"]}),
            "provincias": len({f["provincia"] for f in sel if f["provincia"]}),
            "fuera_de_espana": sum(1 for f in sel if f.get("pais") and f["pais"] != "Spain"),
            "desde": min(f["fecha"] for f in sel if f.get("fecha"))[:4],
            "hasta": max(f["fecha"] for f in sel if f.get("fecha"))[:4],
        }
    return out_lugar, out_artista


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--setlist", required=True, help="setlist_stats.json de fetch_setlist_index")
    ap.add_argument("--conciertos", required=True, help="conciertos.csv de analyze_geography")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    setlist = json.loads(Path(args.setlist).read_text(encoding="utf-8"))
    tax_path = TAXONOMIES_APP if TAXONOMIES_APP.exists() else TAXONOMIES
    lugares = {p["slug"]: p["name"] for p in yaml.safe_load(tax_path.read_text())["places"]}

    with SessionLocal() as db:
        comps, _, _ = catalogo(db)
        toques = _toques_por_composicion(setlist, comps)
        nunca = {
            k for k, c in comps.items() if k not in toques and c["kind"] in ("studio", "ep")
        }
        fila_comp = _comp_de_cada_fila(db, comps)
        discos = _discos(db, setlist, nunca, comps)

    canciones: dict[str, dict] = {}
    for path, k in sorted(fila_comp.items()):
        t = toques.get(k, {})
        canciones[path] = {
            "e": t.get("extremoduro", 0),
            "r": t.get("robe", 0),
            "artista": comps[k]["artista"],
            "once": k in nunca,
            "canonica": comps[k]["path"],
        }

    lugares_out, geo_artista = _geografia(Path(args.conciertos), lugares)

    artistas: dict[str, dict] = {}
    for artista, a in setlist["artistas"].items():
        total = sum(b["toques"] for b in a["discos"])
        fuera = sum(b["toques"] for b in a["discos"] if kw_norm(b["bloque"]) in NO_SON_DISCOS)
        artistas[artista] = {
            "setlists": int(a["setlists"]),
            "toques": total,
            "pct_ajeno": round(100.0 * fuera / total, 1),
            **geo_artista[artista],
        }

    # --- Cuadres: si no cuadran con el ledger, no se escribe nada ---
    for artista, esperado in (("extremoduro", 3295), ("robe", 2286)):
        if artistas[artista]["toques"] != esperado:
            logger.error("toques de %s = %d, el ledger dice %d",
                         artista, artistas[artista]["toques"], esperado)
            return 1
    if len(nunca) != 11:
        logger.error("composiciones sin registro = %d, el ledger dice 11", len(nunca))
        return 1

    ts = [
        "// GENERADO por `api/scripts/pr/build_page_data.py`. No editar a mano: si cambia",
        "// el dato, se regenera el estudio y este fichero. Cifras trazadas en",
        "// `data/estudio/SOURCES.md`. Fuente del directo: setlist.fm (atribución obligatoria,",
        "// enlace sin nofollow).",
        "",
        'import type { DatosPorPagina } from "./tipos-por-pagina";',
        "",
        "export const DATOS: DatosPorPagina = " + json.dumps(
            {"artistas": artistas, "discos": discos, "canciones": canciones,
             "lugares": lugares_out},
            ensure_ascii=False, indent=1,
        ) + ";",
        "",
    ]
    Path(args.out).write_text("\n".join(ts), encoding="utf-8")
    logger.info("%d canciones · %d discos · %d lugares · %s",
                len(canciones), len(discos), len(lugares_out), args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
