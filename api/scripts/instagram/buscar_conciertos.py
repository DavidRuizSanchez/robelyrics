"""Busca conciertos de Extremoduro y Robe en YouTube y los cataloga.

El proyecto no tenía NI UNO: `related_videos.kind='live'` estaba a cero, así que
`video_assets` no podía tener una sola fila de directo. Esto llena ese hueco.

Tres cosas que hace y conviene no deshacer:

- **Descarta los tributos**, y es un descarte duro, no una penalización. La web
  está llena de bandas tributo (Pedrá, Milongas Extremas, Deltó) y publicar una
  como si fuera Extremoduro es el mismo fallo que confundir a dos personas.
- **Saca la fecha y el sitio del título y de la descripción**, que es donde los
  canales de archivo las escriben («Pub El Barco, Palma de Mallorca 17/4/1993»).
  Si no están, se guardan vacías y el post no las mencionará: antes un hueco que
  un dato inventado.
- **Resuelve el canal ANTES de descargar nada**, con la Data API, y aplica el
  veto ahí. Un preselector que descubriera el canal al bajar el vídeo quemaría
  descargas en material impublicable.

Uso:
    python -m scripts.instagram.buscar_conciertos --dry-run     # informe
    python -m scripts.instagram.buscar_conciertos --canales     # solo el resumen por canal
    python -m scripts.instagram.buscar_conciertos
"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from app.db.models import VideoAsset
from app.db.session import SessionLocal
from app.services.instagram import concierto_meta as cm
from app.services.instagram import video_clips
from app.services.youtube_relevance import build_vocab, is_relevant
from scripts.match_youtube import parse_iso8601_duration

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("conciertos")

YT_API = "https://www.googleapis.com/youtube/v3"

# Las consultas salen de las giras que el proyecto YA documenta
# (data/reference/wikipedia_giras_facts.md y las 8 de blog/generate_tour_posts),
# más los recintos del libro. No se inventan sitios ni fechas: se buscan los que
# constan.
CONSULTAS = (
    "Extremoduro concierto completo directo",
    "Extremoduro en directo Las Ventas",
    "Extremoduro directo Palacio de los Deportes",
    "Extremoduro La Cubierta Leganés directo",
    "Extremoduro Festimad directo",
    "Extremoduro concierto 1992 directo",
    "Extremoduro concierto 2002 directo",
    "Robe Iniesta concierto completo directo",
    "Robe Mayéutica concierto completo",
    "Robe Iniesta directo Teatro Romano Mérida",
)
# Un concierto dura. Por debajo de esto suele ser una canción suelta subida a
# trozos, y de ahí no se saca un momento con contexto.
MIN_DURACION_S = 8 * 60

# Que el propio vídeo diga que es un directo. Buscar «concierto» en YouTube
# trae también charlas, reacciones y documentales: sin esto se coló una
# entrevista de una youtuber en el catálogo de conciertos.
import re as _re  # noqa: E402

_ES_DIRECTO = _re.compile(
    r"\b(directo|en vivo|concierto|conciertos|live|gira|festival|"
    r"actuaci[oó]n|bolo|setlist)\b", _re.I
)


def _buscar(client: httpx.Client, key: str, consulta: str) -> dict[str, dict]:
    r = client.get(f"{YT_API}/search", params={
        "part": "snippet", "q": consulta, "type": "video",
        "videoDuration": "long", "maxResults": 20, "key": key,
    })
    if r.status_code != 200:
        logger.warning("search «%s» HTTP %s: %s", consulta, r.status_code, r.text[:140])
        return {}
    return {
        it["id"]["videoId"]: {
            "youtube_id": it["id"]["videoId"],
            "title": it["snippet"]["title"],
            "channel_title": it["snippet"]["channelTitle"],
        }
        for it in r.json().get("items", [])
    }


def _detalles(client: httpx.Client, key: str, ids: list[str]) -> dict[str, dict]:
    """Canal real, duración y DESCRIPCIÓN. 1 unidad de cuota por lote de 50."""
    out: dict[str, dict] = {}
    for i in range(0, len(ids), 50):
        r = client.get(f"{YT_API}/videos", params={
            "part": "snippet,contentDetails", "id": ",".join(ids[i : i + 50]),
            "key": key,
        })
        if r.status_code != 200:
            logger.warning("videos.list HTTP %s: %s", r.status_code, r.text[:140])
            continue
        for it in r.json().get("items", []):
            sn, cd = it.get("snippet", {}), it.get("contentDetails", {})
            out[it["id"]] = {
                "title": sn.get("title"),
                "description": sn.get("description") or "",
                "channel_title": sn.get("channelTitle"),
                "channel_url": (f"https://www.youtube.com/channel/{sn['channelId']}"
                                if sn.get("channelId") else None),
                "duration_s": parse_iso8601_duration(cd.get("duration")),
            }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--canales", action="store_true",
                    help="resume por canal, para decidir de cuáles fiarse")
    args = ap.parse_args()

    key = os.environ.get("YOUTUBE_API_KEY", "")
    if not key:
        raise SystemExit("Falta YOUTUBE_API_KEY")

    with SessionLocal() as db:
        vocab = build_vocab(db)

    candidatos: dict[str, dict] = {}
    with httpx.Client(timeout=30) as client:
        for consulta in CONSULTAS:
            for vid, datos in _buscar(client, key, consulta).items():
                candidatos.setdefault(vid, datos)
        logger.info("Encontrados %d vídeos distintos", len(candidatos))
        detalles = _detalles(client, key, list(candidatos))

    aceptados, descartes = [], {"tributo": 0, "canal": 0, "corto": 0,
                                "sin datos": 0, "no es directo": 0,
                                "no es un bolo": 0, "no son ellos": 0}
    for vid, base in candidatos.items():
        d = detalles.get(vid)
        if not d:
            descartes["sin datos"] += 1
            continue
        titulo, desc = d["title"] or "", d["description"]
        trib = cm.es_tributo(titulo, desc[:400])
        if trib:
            descartes["tributo"] += 1
            logger.debug("tributo (%s): %s", trib, titulo[:70])
            continue
        veto = video_clips.canal_vetado(d["channel_title"] or "")
        if veto or not d["channel_title"]:
            descartes["canal"] += 1
            continue
        if (d["duration_s"] or 0) < MIN_DURACION_S:
            descartes["corto"] += 1
            continue
        if not _ES_DIRECTO.search(f"{titulo}\n{desc[:600]}"):
            descartes["no es directo"] += 1
            logger.debug("no dice que sea directo: %s", titulo[:70])
            continue
        otra_cosa = cm.no_es_concierto(titulo, desc[:400])
        if otra_cosa:
            descartes["no es un bolo"] += 1
            logger.debug("no es un bolo (%s): %s", otra_cosa, titulo[:70])
            continue
        # Y que sean ELLOS. Buscar «concierto completo directo» trae también
        # bolos de Leiva, de Dekameron o de quien sea: YouTube relaciona por
        # público, no por artista. `is_relevant` mira Robe/Extremoduro y los
        # títulos del catálogo, que salen de la BD.
        relevante, motivos = is_relevant(titulo, desc, vocab=vocab,
                                         use_description=True)
        if not relevante:
            descartes["no son ellos"] += 1
            logger.debug("no son ellos: %s", titulo[:70])
            continue
        ev = cm.extraer(titulo, desc)
        aceptados.append({**base, **d, "evento": ev})

    logger.info("Aceptados %d · descartados: %s", len(aceptados), descartes)

    if args.canales:
        por_canal: dict[str, list] = {}
        for a in aceptados:
            por_canal.setdefault(a["channel_title"], []).append(a)
        logger.info("Canales, para decidir de cuáles fiarse:")
        for canal, items in sorted(por_canal.items(), key=lambda kv: -len(kv[1])):
            con_datos = sum(1 for i in items if i["evento"].tiene_algo)
            sensible = video_clips.canal_sensible(canal)
            logger.info("  %-26s %2d vídeos · %d con fecha o lugar%s",
                        canal[:26], len(items), con_datos,
                        f"  ⚠ medio profesional ({sensible})" if sensible else "")
        return

    for a in sorted(aceptados, key=lambda x: -(x["duration_s"] or 0)):
        ev = a["evento"]
        logger.info("  %s | %5d s | %-22s | %-34s | %s",
                    a["youtube_id"], a["duration_s"] or 0, a["channel_title"][:22],
                    ev.como_texto() or "(sin fecha ni lugar)", (a["title"] or "")[:58])

    if args.dry_run:
        logger.info("[dry-run] no se ha guardado nada")
        return

    with SessionLocal() as db:
        nuevos = 0
        for a in aceptados:
            ev = a["evento"]
            fila = db.execute(
                select(VideoAsset).where(VideoAsset.youtube_id == a["youtube_id"])
            ).scalar_one_or_none()
            if fila is None:
                fila = VideoAsset(youtube_id=a["youtube_id"],
                                  url=f"https://www.youtube.com/watch?v={a['youtube_id']}")
                db.add(fila)
                nuevos += 1
            fila.kind = "live_fan"
            fila.title = a["title"]
            fila.description = (a["description"] or "")[:20000]
            fila.channel_title = a["channel_title"]
            fila.channel_url = a["channel_url"]
            fila.duration_s = a["duration_s"]
            fila.event_date = ev.fecha
            fila.event_place = ev.lugar
            fila.event_source = ev.fuente
            fila.vetado = False
            fila.motivo_veto = None
            fila.checked_at = datetime.now(UTC)
        db.commit()
        logger.info("Catálogo de directos: %d aceptados, %d nuevos", len(aceptados), nuevos)


if __name__ == "__main__":
    main()
