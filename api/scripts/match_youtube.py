"""Resuelve `songs.youtube_id` para que la UI enlace directo al video.

Estrategia (de barata a cara en cuota YouTube Data API v3):

  1. CANALES OFICIALES (1 unit por página, ~6 units total):
     - Lista uploads de "Extremoduro - Topic" (auto-generado YouTube Music)
       y "Robe Iniesta - Topic" (incluyen TODAS las canciones de álbum oficiales)
     - Match por título normalizado (sin acentos, lower, sin paréntesis)
     - Marca quality="topic"

  2. CANAL OFICIAL VEVO (si existe, 1 unit por página):
     - "Extremoduro VEVO" para singles con video oficial
     - Marca quality="official"

  3. SEARCH FALLBACK (100 units por canción):
     - Solo para canciones sin match anterior
     - search.list con `q="{title} {artist}"` y `videoCategoryId=10` (música)
     - Marca quality="search"
     - Cuota: 10.000 units/día → max ~95 búsquedas (suficiente para huecos)

Idempotente: si una canción ya tiene youtube_id se salta (a menos que --force).

Ejecución:
  docker compose exec api python -m scripts.match_youtube
  docker compose exec api python -m scripts.match_youtube --force
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from typing import Any

import httpx
from sqlalchemy import update

from app.config import get_settings
from app.db.models import Song
from scripts.research.common import get_session, log, polite_sleep

YT_API = "https://www.googleapis.com/youtube/v3"

# Canales conocidos (resueltos manualmente por handle, ahorra una llamada)
TOPIC_HANDLES = [
    "@extremoduro-topic",         # auto-generado YouTube Music
    "@robeiniesta-topic",
]
SEARCH_QUERIES_FOR_HANDLES = [
    "Extremoduro Topic",
    "Robe Iniesta Topic",
]


def normalize(s: str) -> str:
    """Para matching: lower, sin acentos, sin paréntesis, sin puntuación, espacios colapsados."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\([^)]*\)", " ", s)  # quita paréntesis
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s


def resolve_channel_id(client: httpx.Client, api_key: str, handle: str) -> str | None:
    """Resuelve handle (@xxx) a channelId."""
    r = client.get(
        f"{YT_API}/channels",
        params={"part": "id", "forHandle": handle, "key": api_key},
    )
    if r.status_code == 200 and r.json().get("items"):
        return r.json()["items"][0]["id"]
    return None


def resolve_channel_via_search(client: httpx.Client, api_key: str, query: str) -> str | None:
    r = client.get(
        f"{YT_API}/search",
        params={"part": "id", "type": "channel", "q": query, "maxResults": 1, "key": api_key},
    )
    if r.status_code == 200 and r.json().get("items"):
        return r.json()["items"][0]["id"]["channelId"]
    return None


def list_channel_videos(
    client: httpx.Client, api_key: str, channel_id: str, max_pages: int = 10
) -> list[dict[str, Any]]:
    """Lista uploads del canal: title + videoId."""
    # Obtener uploads playlist
    r = client.get(
        f"{YT_API}/channels",
        params={"part": "contentDetails", "id": channel_id, "key": api_key},
    )
    items = r.json().get("items", [])
    if not items:
        return []
    playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    out: list[dict[str, Any]] = []
    page_token: str | None = None
    pages = 0
    while pages < max_pages:
        params: dict[str, Any] = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        r = client.get(f"{YT_API}/playlistItems", params=params)
        if r.status_code != 200:
            break
        data = r.json()
        for it in data.get("items", []):
            sn = it["snippet"]
            out.append({"title": sn.get("title", ""), "video_id": sn["resourceId"]["videoId"]})
        page_token = data.get("nextPageToken")
        pages += 1
        if not page_token:
            break
    return out


def search_for_song(
    client: httpx.Client, api_key: str, title: str, artist: str
) -> str | None:
    """Búsqueda directa. Cuesta 100 units. Devuelve videoId del primer hit."""
    q = f"{title} {artist}"
    r = client.get(
        f"{YT_API}/search",
        params={
            "part": "id",
            "type": "video",
            "q": q,
            "maxResults": 1,
            "videoCategoryId": "10",  # Música
            "key": api_key,
        },
    )
    if r.status_code != 200:
        log(f"  search HTTP {r.status_code} para '{title}': {r.text[:200]}", "warn")
        return None
    items = r.json().get("items", [])
    if not items:
        return None
    return items[0]["id"]["videoId"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Reescribe los youtube_id ya rellenos")
    parser.add_argument(
        "--no-search-fallback",
        action="store_true",
        help="No gastar cuota en search.list — solo canales oficiales",
    )
    parser.add_argument("--limit-search", type=int, default=80, help="Máx búsquedas vía search.list (cuota)")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.youtube_api_key:
        log("YOUTUBE_API_KEY no configurada", "err")
        return

    n_topic = 0
    n_search = 0
    n_skip = 0
    n_unmatched = 0

    with httpx.Client(timeout=20) as http:
        # 1. Resolver canales oficiales y descargar uploads
        title_to_video: dict[str, tuple[str, str]] = {}  # normalized_title -> (video_id, quality)

        for handle, search_query in zip(TOPIC_HANDLES, SEARCH_QUERIES_FOR_HANDLES, strict=True):
            log(f"resolviendo canal {handle}…")
            ch_id = resolve_channel_id(http, settings.youtube_api_key, handle)
            if not ch_id:
                log(f"  forHandle no resolvió, intentando search…", "warn")
                ch_id = resolve_channel_via_search(http, settings.youtube_api_key, search_query)
            if not ch_id:
                log(f"  ❌ canal {handle} no encontrado", "warn")
                continue
            videos = list_channel_videos(http, settings.youtube_api_key, ch_id)
            log(f"  ✓ {len(videos)} videos del canal")
            for v in videos:
                key = normalize(v["title"])
                if key and key not in title_to_video:
                    title_to_video[key] = (v["video_id"], "topic")

        log(f"índice oficial construido: {len(title_to_video)} videos")

        # 2. Match cada canción contra el índice
        with get_session() as db:
            songs = db.query(Song).all()
            log(f"canciones a procesar: {len(songs)}")

            for song in songs:
                if song.youtube_id and not args.force:
                    n_skip += 1
                    continue
                norm = normalize(song.title)
                if norm in title_to_video:
                    vid, quality = title_to_video[norm]
                    db.execute(
                        update(Song).where(Song.id == song.id).values(
                            youtube_id=vid, youtube_match_quality=quality
                        )
                    )
                    n_topic += 1
                    log(f"  ✓ topic: {song.title} → {vid}")

        # 3. Search fallback solo para los que faltan.
        # Materializamos a tuplas plain para evitar DetachedInstanceError.
        if not args.no_search_fallback:
            with get_session() as db:
                missing = [
                    (s.id, s.title, s.album.artist.name)
                    for s in db.query(Song).filter(Song.youtube_id.is_(None)).all()
                ]
            log(f"canciones sin match: {len(missing)} (gastando cuota search.list)")

            if len(missing) > args.limit_search:
                log(f"  limitando a {args.limit_search} búsquedas (cuota); resto quedará sin match", "warn")

            for song_id, title, artist_name in missing[: args.limit_search]:
                vid = search_for_song(http, settings.youtube_api_key, title, artist_name)
                if vid:
                    with get_session() as db:
                        db.execute(
                            update(Song).where(Song.id == song_id).values(
                                youtube_id=vid, youtube_match_quality="search"
                            )
                        )
                    n_search += 1
                    log(f"  ✓ search: {title} → {vid}")
                else:
                    n_unmatched += 1
                polite_sleep(0.2)

    log(
        f"topic: {n_topic} · search: {n_search} · skip(ya tenían): {n_skip} · sin match: {n_unmatched}",
        "ok",
    )


if __name__ == "__main__":
    main()
