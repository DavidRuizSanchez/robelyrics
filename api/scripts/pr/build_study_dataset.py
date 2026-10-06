"""Construye el dataset del estudio del repertorio. SOLO LECTURA sobre la BD.

    docker compose exec api python -m scripts.pr.build_study_dataset \
        --out /tmp/estudio --setlist /tmp/estudio/setlist_stats.json

Sin `--setlist` calcula solo la capa propia (letras, estribillos, demanda de
búsqueda); con él añade el cruce con el repertorio en directo.

Qué es «propio» y qué es «citado», que es la distinción que sostiene todo el
entregable:

  · PROPIO: el catálogo, las 153 filas de `songs` con sus letras, los 7.039
    versos de `lines`, los estribillos por repetición+dispersión, y la demanda
    de búsqueda real de `data/gsc_page_queries.json`. Nadie más tiene esto.
  · CITADO: las veces que ha sonado cada canción en directo, de setlist.fm, con
    atribución y enlace. No se republica su tabla: se usa para calcular índices
    derivados y se citan cifras puntuales.

Los índices se calculan NORMALIZADOS por número de conciertos. Comparar 78
toques de Robe contra 35 de Extremoduro sin normalizar es el error que tenía el
análisis de partida: Extremoduro tiene 459 setlists registrados y Robe 132, así
que «Si te vas...» suena en el 59% de los conciertos de Robe y en el 7,6% de los
de Extremoduro — ×7,8, no ×2,2.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from collections import defaultdict
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy import select
from sqlalchemy import text as sqltext
from sqlalchemy.orm import Session

from app.db.models import Album, Artist, Song
from app.db.session import SessionLocal
from app.services.instagram import momentos
from app.services.kw_normalize import kw_norm, strip_title_suffix

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

GSC_PATH = Path("/app/data/gsc_page_queries.json")
GSC_FALLBACK = Path(__file__).resolve().parents[2] / "data" / "gsc_page_queries.json"

# Los cajones de la página de discos de setlist.fm que NO son discos. Se
# conservan en el dato (el bloque más tocado por Robe es «Covers», y ahí está
# justo el legado de Extremoduro) pero no cuentan como disco del catálogo.
NO_SON_DISCOS = {"covers", "others"}


# Casado de títulos entre catálogos. Mismos umbrales que `seed_album_tracks`,
# que resuelve exactamente este problema para los tracklists de MusicBrainz.
MIN_FUZZY_RATIO = 0.85
MIN_LARGO_RATIO = 0.70
# Por debajo de esto, un título NO casa por contención: «Mama» dentro de
# «Mama, ya he mamado» casaría, y son canciones distintas. 12 caracteres deja
# pasar «Correcaminos» (que sí es «Correcaminos estate al loro») y para a
# «Mama», «Golfa» y «Salir». Mismo criterio que `kw_normalize`.
MIN_CONTENCION_CHARS = 12
_ARTICULOS = ("la ", "el ", "los ", "las ", "un ", "una ")


def _sin_espacios(k: str) -> str:
    return k.replace(" ", "")


def _sin_articulo(k: str) -> str:
    for a in _ARTICULOS:
        if k.startswith(a):
            return k[len(a):]
    return k


def emparejar(nuestras: dict, ajenas: dict) -> tuple[dict, list, list]:
    """Empareja nuestras composiciones con los títulos de setlist.fm.

    Devuelve `(mapa ajena→nuestra, sin_casar_nuestras, sin_casar_ajenas)`.

    Hace falta porque los dos catálogos escriben distinto la misma canción, y
    sin esto la cifra titular del estudio —cuántas canciones NUNCA sonaron en
    directo— sale inflada. Medido en la primera pasada: de 14 «nunca tocadas»,
    al menos 3 eran fallos de casado («Bri, bri, bli, bli» es «Bribribliblí»,
    «Correcaminos» es «Correcaminos estate al loro», «La Pedrá» es «Pedrá»).

    Lo que NO hace: adivinar. Lo que no casa por una de las cinco reglas sale
    en las listas de sin-casar para que lo revise una persona, igual que
    `seed_album_tracks` deja sin enlazar el corte que no reconoce.
    """
    mapa: dict[str, str] = {}
    libres = dict(nuestras)

    def consumir(ka: str, kn: str) -> None:
        mapa[ka] = kn
        libres.pop(kn, None)

    # 1) exacto
    for ka in list(ajenas):
        if ka in libres:
            consumir(ka, ka)
    # 2) sin espacios («Bri, bri, bli, bli» → «bribriblibli» = «Bribribliblí»)
    idx = {_sin_espacios(k): k for k in libres}
    for ka in (k for k in ajenas if k not in mapa):
        kn = idx.get(_sin_espacios(ka))
        if kn and kn in libres:
            consumir(ka, kn)
    # 3) sin artículo inicial («La Pedrá» → «Pedrá»)
    idx = {_sin_articulo(k): k for k in libres}
    for ka in (k for k in ajenas if k not in mapa):
        kn = idx.get(_sin_articulo(ka))
        if kn and kn in libres:
            consumir(ka, kn)
    # 4) contención, solo con títulos largos
    for ka in (k for k in ajenas if k not in mapa):
        if len(ka) < MIN_CONTENCION_CHARS:
            continue
        for kn in list(libres):
            if len(kn) < MIN_CONTENCION_CHARS:
                continue
            corto, largo = sorted((ka, kn), key=len)
            if corto in largo:
                consumir(ka, kn)
                break
    # 5) difuso con freno de longitud. Sin el freno, «Extremaydura» casa dentro
    #    de «Villancico del Rey de Extremadura» — ya pasó en seed_album_tracks.
    for ka in (k for k in ajenas if k not in mapa):
        mejor, mejor_r = None, 0.0
        for kn in libres:
            if min(len(ka), len(kn)) / max(len(ka), len(kn)) < MIN_LARGO_RATIO:
                continue
            r = SequenceMatcher(None, ka, kn).ratio()
            if r > mejor_r:
                mejor, mejor_r = kn, r
        if mejor and mejor_r >= MIN_FUZZY_RATIO:
            consumir(ka, mejor)

    sin_casar_ajenas = sorted(k for k in ajenas if k not in mapa)
    return mapa, sorted(libres), sin_casar_ajenas


def clave(titulo: str) -> str:
    """Clave de casado entre nuestro catálogo y los títulos de setlist.fm.

    Nuestros títulos llevan sufijo desambiguador («Jesucristo García (Rock
    Transgresivo)», «Tu Corazón (En Directo)») porque la misma composición vive
    en varios discos. Sin quitarlo, la misma canción aparecería tres veces y el
    recuento de «nunca tocadas» saldría inflado — que es justo la cifra que
    cualquier fan va a auditar.
    """
    return kw_norm(strip_title_suffix(titulo))


# --------------------------------------------------------------------------- #
# 1. Catálogo propio
# --------------------------------------------------------------------------- #
def catalogo(db: Session) -> tuple[dict, int, list[dict]]:
    filas = db.execute(
        select(Song.id, Song.title, Song.slug, Album.title, Album.slug, Album.year, Album.kind, Artist.slug)
        .join(Album, Album.id == Song.album_id)
        .join(Artist, Artist.id == Album.artist_id)
    ).all()

    # Una composición puede estar en varios discos (regrabación o directo). La
    # canónica es la del disco MÁS ANTIGUO: es donde se publicó por primera vez.
    comps: dict[str, dict] = {}
    for song_id, titulo, song_slug, disco, album_slug, anyo, kind, artista in filas:
        k = clave(titulo)
        previo = comps.get(k)
        if previo is None or (anyo or 9999) < previo["anyo"]:
            comps[k] = {
                "clave": k,
                "song_id": song_id,
                "titulo": strip_title_suffix(titulo),
                "titulo_bd": titulo,
                "artista": artista,
                "disco": disco,
                "album_slug": album_slug,
                "anyo": anyo or 0,
                "kind": kind,
                "path": f"/{artista}/{album_slug}/{song_slug}",
            }
    # --- Reconciliación de los discos NO de estudio ---
    # `strip_title_suffix` quita TODO lo que va en paréntesis, y en el directo
    # de 1997 el paréntesis lleva parte del título, no un desambiguador:
    # «Correcaminos (Estate al loro) [En Directo]» queda en «Correcaminos» y
    # «La Pedrá (Fragmento) [En Directo]» en «La Pedrá», que no casan con
    # «Correcaminos Estate al Loro» (Agila) ni con «Pedrá» (1995). Resultado:
    # dos composiciones fantasma que además salían en la lista de «nunca
    # tocadas» — la cifra titular del estudio.
    #
    # `album_tracks` es quien debería resolverlo, pero hoy solo cubre los dos
    # «Grandes éxitos y fracasos» y «Bienvenidos al temporal»; el directo de
    # 1997 tiene filas `songs` propias y es anterior a ese modelo.
    #
    # La regla que se aplica no adivina nada: un disco en DIRECTO o un
    # recopilatorio no estrena composiciones. Si un corte suyo casa con una de
    # estudio, es la misma; y si no casa con ninguna, no puede figurar como
    # «canción que nunca se tocó en directo», porque solo existe tocada en
    # directo. Las fusiones se registran para que se puedan auditar.
    de_estudio = {k: c for k, c in comps.items() if c["kind"] in ("studio", "ep")}
    otras = {k: c for k, c in comps.items() if k not in de_estudio}
    fusiones: list[dict] = []
    if otras:
        mapa, _, _ = emparejar(de_estudio, otras)
        for k_otra, k_estudio in mapa.items():
            fusiones.append({
                "absorbida": comps[k_otra]["titulo_bd"],
                "disco_absorbida": comps[k_otra]["disco"],
                "en": comps[k_estudio]["titulo_bd"],
                "disco_en": comps[k_estudio]["disco"],
            })
            comps.pop(k_otra, None)
    if fusiones:
        logger.info("reconciliadas %d composiciones de discos no-estudio:", len(fusiones))
        for f in fusiones:
            logger.info("   «%s» (%s) → «%s» (%s)",
                        f["absorbida"], f["disco_absorbida"], f["en"], f["disco_en"])

    logger.info("catálogo: %d filas en songs → %d composiciones distintas", len(filas), len(comps))
    # El nº de filas viaja aparte: es el denominador que NO hay que usar. Las
    # 153 filas de `songs` incluyen 33 regrabaciones y versiones en directo de
    # la misma composición.
    return comps, len(filas), fusiones


# --------------------------------------------------------------------------- #
# 2. Anatomía de la letra (exclusivo)
# --------------------------------------------------------------------------- #
def anatomia(db: Session, canonicas: set[int]) -> dict:
    """Métricas de la letra, SOLO sobre las filas canónicas de cada composición.

    Esto no es un refinamiento: sin filtrar, la misma composición se cuenta una
    vez por disco en que aparece. «Tú en tu casa, nosotros en la hoguera» vive
    en tres filas (el disco de 1990, la regrabación de Rock Transgresivo de 1994
    y el directo de 1997), así que su verso «Tú en tu casa» salía con 35
    repeticiones y encabezaba el ranking de «verso más repetido de la obra»
    cuando lo que medía era cuántas veces se regrabó el disco. Por el mismo
    motivo el porcentaje de versos repetidos salía inflado.
    """
    versos, distintos, canciones_con_letra, largo_medio = db.execute(sqltext(
        """
        select count(*), count(distinct l.text), count(distinct l.song_id),
               avg(length(l.text))
        from lines l
        where l.song_id = any(:ids)
        """
    ), {"ids": list(canonicas)}).one()

    # El verso más repetido de toda la obra, y en cuántas canciones aparece.
    top_versos = db.execute(sqltext(
        """
        select l.text, count(*) as n, count(distinct l.song_id) as canciones
        from lines l
        where length(l.text) > 12 and l.song_id = any(:ids)
        group by l.text
        order by n desc, l.text
        limit 25
        """
    ), {"ids": list(canonicas)}).all()

    # Canción con más versos.
    mas_versos = db.execute(sqltext(
        """
        select s.title, count(*) as n
        from lines l join songs s on s.id = l.song_id
        where l.song_id = any(:ids)
        group by s.title order by n desc limit 10
        """
    ), {"ids": list(canonicas)}).all()

    # Estrofas: `lines.stanza_index` existe y no lo explotaba nadie.
    estrofas = db.execute(sqltext(
        """
        select count(*) filter (where stanza_index is not null),
               count(distinct song_id) filter (where stanza_index is not null)
        from lines where song_id = any(:ids)
        """
    ), {"ids": list(canonicas)}).one()

    # Densidad de canto: versos por minuto CANTADO.
    #
    # El primer intento dividía por la duración del vídeo y dio cobertura CERO:
    # `songs.youtube_duration_sec` está vacío en las 153 filas y `duration_sec`
    # solo en 8. Habría salido un gráfico en blanco.
    #
    # Lo que sí hay es `lines.start_seconds` (4.337 versos en 133 canciones, vía
    # LRCLIB), y mide algo mejor: el tramo entre el primer y el último verso es
    # el CANTO, sin la intro ni los solos. «Versos por minuto de duración» y
    # «versos por minuto cantado» no son lo mismo, y el segundo es el que dice
    # algo sobre la letra.
    densidad = db.execute(sqltext(
        """
        select s.title,
               count(l.id) as versos,
               round((max(l.start_seconds) - min(l.start_seconds))::numeric, 1) as tramo_s,
               round(count(l.id)::numeric * 60
                     / nullif(max(l.start_seconds) - min(l.start_seconds), 0), 2) as vpm
        from songs s join lines l on l.song_id = s.id
        where l.start_seconds is not null and s.id = any(:ids)
        group by s.title
        having count(l.id) >= 8
           and (max(l.start_seconds) - min(l.start_seconds)) >= 60
        order by vpm desc
        """
    ), {"ids": list(canonicas)}).all()

    # Estribillos: MISMA fórmula que `momentos.cargar_catalogo` (repetición ≥ 3
    # y dispersión ≥ 0,35), con sus propios umbrales importados para que si
    # alguien los recalibra allí, esto los siga. No se llama a esa función
    # directamente por dos motivos:
    #   · no filtra por composición canónica, y aquí hace falta;
    #   · colapsa por verso normalizado (`setdefault`), que vale para casar
    #     audio pero aquí esconde el dato: el mismo verso puede ser estribillo
    #     de dos canciones y son dos estribillos.
    repetidos = db.execute(sqltext(
        """
        with largo as (
            select song_id, max(line_index)::float + 1 as lineas
            from lines where song_id = any(:ids) group by song_id
        )
        select s.title, l.text, count(*) as n,
               (max(l.line_index) - min(l.line_index)) / max(largo.lineas) as dispersion
        from lines l
        join songs s on s.id = l.song_id
        join largo on largo.song_id = l.song_id
        where length(l.text) > 12 and l.song_id = any(:ids)
        group by s.title, l.text
        having count(*) >= :minimo
        """
    ), {"ids": list(canonicas), "minimo": momentos.REPETICIONES_ESTRIBILLO}).all()

    estribillos = [
        {"cancion": t, "verso": txt, "repeticiones": n, "dispersion": round(float(d), 2)}
        for t, txt, n, d in repetidos
        if (d or 0) >= momentos.DISPERSION_MIN
    ]
    descartados = len(repetidos) - len(estribillos)

    return {
        "versos_totales": versos,
        "versos_distintos": distintos,
        "pct_repeticion": round(100.0 * (versos - distintos) / versos, 1) if versos else None,
        "canciones_con_letra": canciones_con_letra,
        "largo_medio_verso_chars": round(float(largo_medio), 1) if largo_medio else None,
        "versos_con_stanza_index": estrofas[0],
        "canciones_con_stanza_index": estrofas[1],
        # Dos recuentos porque son dos cosas, y mezclarlos ya dio dos cifras
        # distintas para lo mismo: 250 pares (verso, canción) frente a 220
        # versos distintos. El publicable es el par: un verso que es estribillo
        # de dos canciones son dos estribillos.
        "estribillos_pares_verso_cancion": len(estribillos),
        "estribillos_versos_distintos": len({e["verso"] for e in estribillos}),
        "canciones_con_estribillo": len({e["cancion"] for e in estribillos}),
        "versos_repetidos_candidatos": len(repetidos),
        "descartados_por_dispersion": descartados,
        "umbrales": {
            "repeticiones_minimas": momentos.REPETICIONES_ESTRIBILLO,
            "dispersion_minima": momentos.DISPERSION_MIN,
        },
        "top_versos_repetidos": [
            {"verso": t, "repeticiones": n, "canciones": c} for t, n, c in top_versos
        ],
        "canciones_con_mas_versos": [{"titulo": t, "versos": n} for t, n in mas_versos],
        "densidad_canto": {
            "cobertura_canciones": len(densidad),
            "metrica": "versos por minuto de tramo cantado (primer→último verso)",
            "top": [
                {"titulo": t, "versos": v, "tramo_s": float(d), "versos_por_minuto": float(vpm)}
                for t, v, d, vpm in densidad[:10]
            ],
            "cola": [
                {"titulo": t, "versos": v, "tramo_s": float(d), "versos_por_minuto": float(vpm)}
                for t, v, d, vpm in densidad[-10:]
            ],
        },
    }


# --------------------------------------------------------------------------- #
# 3. Demanda de búsqueda propia (GSC)
# --------------------------------------------------------------------------- #
def demanda(comps: dict) -> dict:
    ruta = GSC_PATH if GSC_PATH.exists() else GSC_FALLBACK
    if not ruta.exists():
        logger.warning("sin fichero de GSC en %s: se omite la demanda", ruta)
        return {}
    bruto = json.loads(ruta.read_text(encoding="utf-8"))
    por_path = bruto.get("pages", {})

    por_clave: dict[str, dict] = {}
    for comp in comps.values():
        filas = por_path.get(comp["path"]) or []
        if not filas:
            continue
        por_clave[comp["clave"]] = {
            "path": comp["path"],
            "impresiones": sum(f.get("impressions", 0) for f in filas),
            "clics": sum(f.get("clicks", 0) for f in filas),
            "consultas": len(filas),
        }
    logger.info(
        "demanda: %d de %d composiciones tienen datos de GSC (periodo %s)",
        len(por_clave), len(comps), bruto.get("period"),
    )
    return {"periodo": bruto.get("period"), "site": bruto.get("site"), "por_cancion": por_clave}


# --------------------------------------------------------------------------- #
# 4. Cruce con el repertorio en directo (citado)
# --------------------------------------------------------------------------- #
def repertorio(setlist: dict, comps: dict, dem: dict) -> dict:
    arts = setlist["artistas"]
    setlists = {s: a["setlists"] for s, a in arts.items()}

    # toques por clave y por artista
    toques: dict[str, dict[str, int]] = defaultdict(dict)
    titulos_setlist: dict[str, str] = {}
    for slug, a in arts.items():
        for c in a["canciones"]:
            k = clave(c["titulo"])
            toques[k][slug] = c["toques"]
            titulos_setlist.setdefault(k, c["titulo"])

    # Los dos catálogos escriben distinto la misma canción: hay que emparejar
    # antes de cruzar, o «nunca tocadas» cuenta fallos de casado como hallazgos.
    mapa, sin_casar_nuestras, sin_casar_ajenas = emparejar(comps, dict(toques))
    logger.info(
        "casado: %d de %d títulos de setlist.fm emparejados · %d composiciones "
        "nuestras sin aparecer · %d títulos suyos sin casar (versiones y medleys)",
        len(mapa), len(toques), len(sin_casar_nuestras), len(sin_casar_ajenas),
    )

    unificado = []
    for k, por_art in toques.items():
        total = sum(por_art.values())
        comp = comps.get(mapa[k]) if k in mapa else None
        fila = {
            "clave": comp["clave"] if comp else k,
            "titulo_setlistfm": titulos_setlist[k],
            "titulo": comp["titulo"] if comp else titulos_setlist[k],
            "en_nuestro_catalogo": comp is not None,
            "disco": comp["disco"] if comp else None,
            "anyo": comp["anyo"] if comp else None,
            "path": comp["path"] if comp else None,
            "toques_extremoduro": por_art.get("extremoduro", 0),
            "toques_robe": por_art.get("robe", 0),
            "toques_total": total,
        }
        # Índice de Resurrección: compara PRESENCIA en el repertorio, no toques
        # brutos. `pct` = en qué porcentaje de los conciertos registrados de esa
        # formación suena la canción.
        pe = 100.0 * fila["toques_extremoduro"] / setlists["extremoduro"]
        pr = 100.0 * fila["toques_robe"] / setlists["robe"]
        fila["pct_conciertos_extremoduro"] = round(pe, 1)
        fila["pct_conciertos_robe"] = round(pr, 1)
        fila["indice_resurreccion"] = round(pr / pe, 1) if pe > 0 and pr > 0 else None
        unificado.append(fila)
    unificado.sort(key=lambda f: -f["toques_total"])

    # --- Canciones NUNCA tocadas: las que no ha reclamado ningún título suyo ---
    nunca = [
        {k2: v for k2, v in comps[k].items() if k2 not in ("titulo_bd", "song_id")}
        for k in sin_casar_nuestras
        if comps[k]["kind"] in ("studio", "ep")
    ]
    nunca.sort(key=lambda c: (c["anyo"], c["titulo"]))
    for c in nunca:
        d = dem.get("por_cancion", {}).get(c["clave"])
        c["impresiones_gsc"] = d["impresiones"] if d else 0

    # --- Deuda del Setlist: demanda propia frente a presencia en directo ---
    deuda = []
    for f in unificado:
        if not f["en_nuestro_catalogo"]:
            continue
        d = dem.get("por_cancion", {}).get(f["clave"])
        if not d or d["impresiones"] < 50:
            continue
        pct_max = max(f["pct_conciertos_extremoduro"], f["pct_conciertos_robe"])
        deuda.append({
            "titulo": f["titulo"],
            "disco": f["disco"],
            "path": f["path"],
            "impresiones_gsc": d["impresiones"],
            "clics_gsc": d["clics"],
            "toques_total": f["toques_total"],
            "pct_conciertos_max": pct_max,
            # Impresiones por cada punto de presencia en el repertorio. Alto =
            # la gente la busca mucho y en directo apenas suena.
            "deuda": round(d["impresiones"] / max(pct_max, 0.2), 1),
        })
    deuda.sort(key=lambda f: -f["deuda"])

    # --- Discos: cuánto pesa cada bloque, y cuánto pesa el legado ---
    discos = {}
    for slug, a in arts.items():
        total = a["toques_totales"]
        bloques = [
            {
                "bloque": b["bloque"],
                "toques": b["toques"],
                "pct": round(100.0 * b["toques"] / total, 1),
                "es_disco": b["bloque"].lower() not in NO_SON_DISCOS,
            }
            for b in a["discos"]
        ]
        legado = sum(b["toques"] for b in bloques if not b["es_disco"])
        discos[slug] = {
            "toques_totales": total,
            "bloques": bloques,
            "toques_fuera_de_discos_propios": legado,
            "pct_fuera_de_discos_propios": round(100.0 * legado / total, 1),
        }

    return {
        "casado": {
            "titulos_setlistfm": len(toques),
            "emparejados": len(mapa),
            "nuestras_sin_aparecer": len(sin_casar_nuestras),
            "suyos_sin_casar": sin_casar_ajenas,
        },
        "setlists_registrados": setlists,
        "canciones_distintas": {s: len(a["canciones"]) for s, a in arts.items()},
        "unificado": unificado,
        "nunca_tocadas": nunca,
        "deuda_setlist": deuda,
        "discos": discos,
        "conciertos_por_anyo": {s: a["anyos"] for s, a in arts.items()},
        "giras": {s: a["giras"] for s, a in arts.items()},
        "series_completas": {
            s: {"anyos": a["anyos_completos"], "giras": a["giras_completas"]}
            for s, a in arts.items()
        },
    }


def _csv(destino: Path, filas: list[dict]) -> None:
    if not filas:
        logger.warning("sin filas para %s", destino.name)
        return
    campos = list(filas[0])
    with destino.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        for f in filas:
            w.writerow({c: f.get(c) for c in campos})
    logger.info("escrito %s (%d filas)", destino.name, len(filas))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    ap.add_argument("--setlist", help="setlist_stats.json de fetch_setlist_index")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        comps, filas_songs, fusiones = catalogo(db)
        canonicas = {c["song_id"] for c in comps.values()}
        anat = anatomia(db, canonicas)
        dem = demanda(comps)

        rep = {}
        if args.setlist:
            setlist = json.loads(Path(args.setlist).read_text(encoding="utf-8"))
            rep = repertorio(setlist, comps, dem)

    payload = {
        "generado_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "catalogo": {
            "filas_songs": filas_songs,
            "composiciones_distintas": len(comps),
            "reconciliadas_desde_no_estudio": fusiones,
        },
        "anatomia_letra": anat,
        "demanda": {k: v for k, v in dem.items() if k != "por_cancion"},
        "repertorio": {k: v for k, v in rep.items() if k not in ("unificado", "nunca_tocadas", "deuda_setlist")},
    }
    (out / "estudio.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if rep:
        _csv(out / "repertorio_unificado.csv", rep["unificado"])
        _csv(out / "nunca_tocadas.csv", rep["nunca_tocadas"])
        _csv(out / "deuda_setlist.csv", rep["deuda_setlist"])
    _csv(out / "versos_mas_repetidos.csv", anat["top_versos_repetidos"])

    # ---- resumen por consola, para revisar sin abrir el JSON ----
    print()
    print(f"CATÁLOGO            {filas_songs} filas en songs → {len(comps)} composiciones distintas")
    print(f"VERSOS              {anat['versos_totales']} totales · {anat['versos_distintos']} distintos "
          f"· {anat['pct_repeticion']}% son repeticiones")
    print(f"VERSOS REPETIDOS    {anat['versos_repetidos_candidatos']} candidatos "
          f"→ {anat['descartados_por_dispersion']} descartados por no volver")
    print(f"ESTRIBILLOS         {anat['estribillos_pares_verso_cancion']} pares verso-canción "
          f"({anat['estribillos_versos_distintos']} versos distintos) en "
          f"{anat['canciones_con_estribillo']} de {anat['canciones_con_letra']} composiciones")
    if anat["top_versos_repetidos"]:
        v = anat["top_versos_repetidos"][0]
        print(f"VERSO MÁS REPETIDO  «{v['verso']}» ×{v['repeticiones']}")
    if rep:
        print(f"SETLISTS            {rep['setlists_registrados']}")
        print(f"NUNCA TOCADAS       {len(rep['nunca_tocadas'])} de {len(comps)} composiciones")
        for s, d in rep["discos"].items():
            print(f"  {s:<12} {d['pct_fuera_de_discos_propios']}% de los toques fuera de sus discos propios")
        print("TOP 5 RESURRECCIÓN")
        for f in sorted((f for f in rep["unificado"] if f["indice_resurreccion"]),
                        key=lambda f: -f["indice_resurreccion"])[:5]:
            print(f"  ×{f['indice_resurreccion']:<5} {f['titulo'][:40]:<42} "
                  f"{f['pct_conciertos_extremoduro']}% → {f['pct_conciertos_robe']}%")
        print("TOP 5 DEUDA DEL SETLIST")
        for f in rep["deuda_setlist"][:5]:
            print(f"  {f['deuda']:<9} {f['titulo'][:40]:<42} {f['impresiones_gsc']} impr · "
                  f"{f['pct_conciertos_max']}% conciertos")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
