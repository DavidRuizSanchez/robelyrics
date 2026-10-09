"""Busca en YouTube directos de UNA canción y los cataloga para clips.

Criterio de David (09-10-2026): un clip es una canción cortada en su estribillo,
y el texto del post es el de esa canción. Un vídeo de una sola canción ya dice
de qué canción es —su título la nombra—, así que no hay que transcribir
conciertos enteros para adivinarlo: el daemon solo escucha sus primeros minutos
para encontrar el estribillo (`estribillo.localizar`).

Un vídeo se acepta solo si:
  - su título nombra ESA canción y ninguna otra del catálogo (un popurrí no
    sirve: no se sabría qué estribillo buscar);
  - nombra a Extremoduro o a Robe, y dice que es un directo;
  - no es una banda tributo ni de un canal vetado (mismos filtros que
    `buscar_conciertos`);
  - dura entre 2 y 12 minutos (una canción, no un bolo ni un corte de 30 s).

Cuota: cada búsqueda cuesta 100 unidades de las 10.000 diarias de la Data API,
así que va por lotes (`--limit`) y empieza por las canciones sin vídeo todavía.

Uso:
    python -m scripts.instagram.buscar_canciones_directo --dry-run --limit 10
    python -m scripts.instagram.buscar_canciones_directo --limit 25
"""
from __future__ import annotations

import argparse
import logging
import os
import re
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from app.db.models import Album, Artist, Song, VideoAsset
from app.db.session import SessionLocal
from app.services.instagram import concierto_meta as cm
from app.services.instagram import video_clips
from app.services.lyric_guard import normalize
from app.services.versiones import es_original
from scripts.instagram.buscar_conciertos import _ES_DIRECTO, YT_API, _detalles

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("canciones")

MIN_S, MAX_S = 120, 12 * 60
POR_CANCION = 3
_ARTISTA = re.compile(r"\b(extremoduro|robe)\b", re.I)
_SUFIJO = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]\s*$")


def _titulo_base(titulo: str) -> str:
    """«Pepe Botika (¿Dónde están mis amigos?)» → «pepe botika»."""
    t = _SUFIJO.sub("", titulo or "") or titulo or ""
    return normalize(t)


def _nombra(texto_norm: str, titulo_norm: str) -> bool:
    return bool(titulo_norm) and re.search(
        r"(?<![a-z0-9ñ])" + re.escape(titulo_norm) + r"(?![a-z0-9ñ])", texto_norm) is not None


def canciones_del_titulo(titulo_video: str, catalogo: set[str]) -> set[str]:
    """Qué canciones del catálogo nombra el título de un vídeo. Los títulos de
    menos de 5 letras no cuentan: «Mama» o «Ama» aparecen en cualquier título,
    y una canción mal identificada es peor que una canción sin clip."""
    tv = normalize(titulo_video)
    nombradas = {t for t in catalogo if len(t) >= 5 and _nombra(tv, t)}
    # Un título contenido en otro («Salir» dentro de «Salir de la ciudad») no
    # es una segunda canción.
    return {t for t in nombradas if not any(t != o and t in o for o in nombradas)}


def aceptar(video: dict, cancion: str, catalogo: set[str]) -> str | None:
    """None si el vídeo vale para esa canción (`cancion`: título de la BD); si
    no, el motivo. Se compara por título BASE: «Extremaydura» es la misma
    canción en los dos discos gemelos de 1990 y 1994."""
    titulo, desc = video.get("title") or "", video.get("description") or ""
    nombradas = canciones_del_titulo(titulo, catalogo)
    if _titulo_base(cancion) not in nombradas:
        return "el título no nombra la canción"
    if len(nombradas) > 1:
        return "el título nombra varias canciones"
    if not _ARTISTA.search(f"{titulo}\n{video.get('channel_title') or ''}\n{desc[:300]}"):
        return "no dice que sea Extremoduro o Robe"
    if not _ES_DIRECTO.search(f"{titulo}\n{desc[:600]}"):
        return "no dice que sea un directo"
    if cm.es_tributo(titulo, desc[:400]):
        return "tributo"
    if video_clips.canal_vetado(video.get("channel_title") or "") or not video.get("channel_title"):
        return "canal vetado"
    if not (MIN_S <= (video.get("duration_s") or 0) <= MAX_S):
        return "duración fuera de 2-12 min"
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=25, help="canciones por pasada")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    key = os.environ.get("YOUTUBE_API_KEY", "")
    if not key:
        raise SystemExit("Falta YOUTUBE_API_KEY")

    with SessionLocal() as db:
        filas = db.execute(
            select(Song, Album, Artist).join(Album, Song.album_id == Album.id)
            .join(Artist, Album.artist_id == Artist.id).order_by(Song.id)
        ).all()
        originales = [(s, ar) for s, al, ar in filas if es_original(s, al)]
        catalogo = {_titulo_base(s.title) for s, _ in originales}
        con_video = {sid for (sid,) in db.execute(
            select(VideoAsset.song_id).where(VideoAsset.kind == "live_song",
                                             VideoAsset.song_id.is_not(None))).all()}
        lote = [(s, ar) for s, ar in originales if s.id not in con_video][: args.limit]

    aceptados: list[dict] = []
    descartes: dict[str, int] = {}
    with httpx.Client(timeout=30) as client:
        for song, artist in lote:
            consulta = f"{artist.name} {_SUFIJO.sub('', song.title)} directo"
            r = client.get(f"{YT_API}/search", params={
                "part": "snippet", "q": consulta, "type": "video",
                "maxResults": 10, "key": key,
            })
            if r.status_code != 200:
                logger.warning("search «%s» HTTP %s: %s", consulta, r.status_code, r.text[:140])
                if r.status_code == 403:
                    break   # cuota agotada: lo que quede, en la próxima pasada
                continue
            ids = [it["id"]["videoId"] for it in r.json().get("items", [])]
            detalles = _detalles(client, key, ids)
            n = 0
            for vid in ids:
                d = detalles.get(vid)
                if not d:
                    continue
                motivo = aceptar(d, song.title, catalogo)
                if motivo:
                    descartes[motivo] = descartes.get(motivo, 0) + 1
                    continue
                ev = cm.extraer(d["title"] or "", d["description"] or "")
                aceptados.append({"youtube_id": vid, "song_id": song.id, "cancion": song.title,
                                  "evento": ev, **d})
                n += 1
                if n >= POR_CANCION:
                    break
            logger.info("«%s»: %d vídeo(s)", song.title, n)

    logger.info("Aceptados %d · descartes: %s", len(aceptados), descartes)
    for a in aceptados:
        logger.info("  %s | %-28s | %4ds | %-20s | %s", a["youtube_id"], a["cancion"][:28],
                    a["duration_s"] or 0, (a["channel_title"] or "")[:20], (a["title"] or "")[:60])
    if args.dry_run:
        logger.info("[dry-run] no se ha guardado nada")
        return

    with SessionLocal() as db:
        nuevos = 0
        for a in aceptados:
            fila = db.execute(select(VideoAsset).where(
                VideoAsset.youtube_id == a["youtube_id"])).scalar_one_or_none()
            if fila is None:
                fila = VideoAsset(youtube_id=a["youtube_id"],
                                  url=f"https://www.youtube.com/watch?v={a['youtube_id']}")
                db.add(fila)
                nuevos += 1
            elif fila.kind != "live_song":
                continue   # ya catalogado como concierto o entrevista: no se pisa
            ev = a["evento"]
            fila.kind = "live_song"
            fila.song_id = a["song_id"]
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
        logger.info("Directos de una canción: %d aceptados, %d nuevos", len(aceptados), nuevos)


if __name__ == "__main__":
    main()
