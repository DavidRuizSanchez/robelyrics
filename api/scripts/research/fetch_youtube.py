"""Descarga transcripts y top-comments de canales fan de YouTube.

Lee `data/sources.yaml` sección `youtube` y para cada canal:

  1. Resuelve el channelId con YouTube Data API v3 (forHandle / forUsername).
  2. Lista todos los videos del canal (uploads playlist).
  3. Por cada video:
       - Descarga transcript en español (con youtube-transcript-api).
       - Descarga top-10 comentarios destacados (filtro: >300 chars, ≥10 likes).
  4. Cada transcript / comentario se guarda como InterpretationSource.

Cuota YouTube Data API: ~10k units/día gratis. Cada listado cuesta 1 unit.
Cada canal de Juancares (~50 videos) consume ~100 units → sobra mucho.

Ejecución: docker compose exec api python -m scripts.research.fetch_youtube
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime
from typing import Any

import httpx
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from app.config import get_settings
from scripts.research.common import (
    clean_text,
    get_session,
    load_sources_yaml,
    log,
    polite_sleep,
    upsert_source,
)

YT_API = "https://www.googleapis.com/youtube/v3"


# --------------------------------------------------------------------------- #
# Resolución de canal
# --------------------------------------------------------------------------- #
def extract_handle(url: str) -> str | None:
    """Extrae el handle (@nombre) o username de una URL de canal de YouTube."""
    if "@" in url:
        m = re.search(r"@([\w-]+)", url)
        if m:
            return m.group(1)
    if "/c/" in url:
        m = re.search(r"/c/([\w-]+)", url)
        if m:
            return m.group(1)
    if "/user/" in url:
        m = re.search(r"/user/([\w-]+)", url)
        if m:
            return m.group(1)
    return None


def resolve_channel_id(client: httpx.Client, api_key: str, handle: str) -> str | None:
    """Convierte handle (@juancaraes o juancaraes) a channelId real."""
    # 1. forHandle (handles modernos: @nombre)
    r = client.get(
        f"{YT_API}/channels",
        params={"part": "id", "forHandle": f"@{handle.lstrip('@')}", "key": api_key},
    )
    if r.status_code == 200 and r.json().get("items"):
        return r.json()["items"][0]["id"]

    # 2. forUsername (legacy)
    r = client.get(
        f"{YT_API}/channels",
        params={"part": "id", "forUsername": handle, "key": api_key},
    )
    if r.status_code == 200 and r.json().get("items"):
        return r.json()["items"][0]["id"]

    # 3. search (último recurso)
    r = client.get(
        f"{YT_API}/search",
        params={"part": "id", "type": "channel", "q": handle, "maxResults": 1, "key": api_key},
    )
    if r.status_code == 200 and r.json().get("items"):
        return r.json()["items"][0]["id"]["channelId"]

    return None


def get_uploads_playlist(client: httpx.Client, api_key: str, channel_id: str) -> str | None:
    r = client.get(
        f"{YT_API}/channels",
        params={"part": "contentDetails", "id": channel_id, "key": api_key},
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        return None
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def list_videos(client: httpx.Client, api_key: str, playlist_id: str, limit: int | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": api_key,
        }
        if page_token:
            params["pageToken"] = page_token
        r = client.get(f"{YT_API}/playlistItems", params=params)
        r.raise_for_status()
        data = r.json()
        for it in data.get("items", []):
            sn = it["snippet"]
            out.append(
                {
                    "video_id": sn["resourceId"]["videoId"],
                    "title": sn.get("title"),
                    "published_at": sn.get("publishedAt"),
                    "description": sn.get("description"),
                }
            )
            if limit and len(out) >= limit:
                return out
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return out


# --------------------------------------------------------------------------- #
# Transcripts
# --------------------------------------------------------------------------- #
# Singleton del cliente — la API nueva (1.2.x) requiere instanciar
_yt_api = YouTubeTranscriptApi()


def fetch_transcript(video_id: str) -> str | None:
    try:
        fetched = _yt_api.fetch(video_id, languages=["es", "es-ES", "en"])
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable, CouldNotRetrieveTranscript):
        return None
    except Exception as e:  # noqa: BLE001
        log(f"transcript error {video_id}: {type(e).__name__}: {e}", "warn")
        return None
    text = " ".join(s.text for s in fetched.snippets if s.text)
    return clean_text(text)


# --------------------------------------------------------------------------- #
# Comentarios destacados
# --------------------------------------------------------------------------- #
def fetch_top_comments(client: httpx.Client, api_key: str, video_id: str, n: int = 10) -> list[dict[str, Any]]:
    try:
        r = client.get(
            f"{YT_API}/commentThreads",
            params={
                "part": "snippet",
                "videoId": video_id,
                "order": "relevance",
                "maxResults": min(n * 3, 50),  # pedimos margen para filtrar
                "textFormat": "plainText",
                "key": api_key,
            },
        )
        if r.status_code in (403, 404):
            # Comentarios desactivados o video no accesible
            return []
        r.raise_for_status()
        items = r.json().get("items", [])
    except httpx.HTTPError as e:
        log(f"comments error {video_id}: {e}", "warn")
        return []

    out: list[dict[str, Any]] = []
    for it in items:
        sn = it["snippet"]["topLevelComment"]["snippet"]
        text = sn.get("textDisplay") or ""
        likes = int(sn.get("likeCount") or 0)
        # Filtros de calidad
        if len(text) < 300 or likes < 10:
            continue
        out.append(
            {
                "id": it["id"],
                "author": sn.get("authorDisplayName"),
                "text": text,
                "likes": likes,
                "published_at": sn.get("publishedAt"),
            }
        )
        if len(out) >= n:
            break
    return out


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def parse_iso(dt: str | None) -> datetime | None:
    if not dt:
        return None
    try:
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    except ValueError:
        return None


def _run_from_songs(http_client: httpx.Client, api_key: str) -> None:
    """Modo `--from-songs`: itera por songs.youtube_id y descarga top-comments.

    Cada comment se inserta con referenced_song_ids=[song_id] precargado, sin
    necesidad de pasar por link_sources_to_songs después. Útil porque las
    canciones tienen videoIds canónicos (Topic / oficiales) y los comments
    suelen tratar de la canción específica del vídeo.
    """
    from app.db.models import Song
    from scripts.research.common import get_session

    with get_session() as db:
        songs = (
            db.query(Song)
            .filter(Song.youtube_id.is_not(None))
            .order_by(Song.id)
            .all()
        )
        # Materializar a tuples para no depender de la sesión.
        targets = [(s.id, s.title, s.youtube_id) for s in songs]

    log(f"from-songs: {len(targets)} canciones con youtube_id")
    total_comments = 0

    for song_id, title, vid in targets:
        video_url = f"https://www.youtube.com/watch?v={vid}"
        with get_session() as db:
            comments = fetch_top_comments(http_client, api_key, vid, n=10)
            for c in comments:
                upsert_source(
                    db,
                    kind="youtube_comment",
                    url=f"{video_url}&lc={c['id']}",
                    title=f"Comment on: {title}",
                    author=c.get("author"),
                    published_at=parse_iso(c.get("published_at")),
                    content_raw=c["text"],
                    content_clean=clean_text(c["text"]),
                    quality_score=min(1.0, 0.4 + c["likes"] / 500),
                    referenced_song_ids=[song_id],
                )
                total_comments += 1
        polite_sleep(0.3)

    log(f"comments from-songs: {total_comments}", "ok")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-videos", type=int, default=None, help="Máx videos por canal (smoke test).")
    parser.add_argument("--skip-comments", action="store_true", help="No descargar comentarios.")
    parser.add_argument(
        "--from-songs",
        action="store_true",
        help="En lugar de iterar por canales, iterar por songs.youtube_id y bajar top-comments por canción.",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.youtube_api_key:
        log("YOUTUBE_API_KEY no configurada — abortando", "err")
        return

    if args.from_songs:
        with httpx.Client(timeout=20) as http_client:
            _run_from_songs(http_client, settings.youtube_api_key)
        return

    sources = load_sources_yaml()
    channels = sources.get("youtube", []) or []
    channels = [c for c in channels if c.get("status") == "active"]
    if not channels:
        log("Sin canales activos en sources.yaml", "warn")
        return

    total_transcripts = 0
    total_comments = 0

    with httpx.Client(timeout=20) as http_client:
        for ch in channels:
            url = ch["url"]
            handle = extract_handle(url)
            if not handle:
                log(f"no handle parseable en {url}", "warn")
                continue
            log(f"resolviendo canal '{handle}'...")
            channel_id = resolve_channel_id(http_client, settings.youtube_api_key, handle)
            if not channel_id:
                log(f"  canal no resuelto", "warn")
                continue
            playlist_id = get_uploads_playlist(http_client, settings.youtube_api_key, channel_id)
            if not playlist_id:
                log(f"  uploads playlist no disponible", "warn")
                continue
            videos = list_videos(http_client, settings.youtube_api_key, playlist_id, limit=args.limit_videos)
            log(f"  {len(videos)} videos")

            for v in videos:
                vid = v["video_id"]
                video_url = f"https://www.youtube.com/watch?v={vid}"
                published = parse_iso(v["published_at"])

                # Una sesión por video → commit al cerrar el `with`. Si crash
                # mid-canal solo perdemos el video en curso.
                with get_session() as db:
                    transcript = fetch_transcript(vid)
                    if transcript and len(transcript) > 200:
                        upsert_source(
                            db,
                            kind="youtube_transcript",
                            url=video_url,
                            title=v["title"],
                            author=ch["name"],
                            published_at=published,
                            content_raw=transcript,
                            content_clean=transcript,
                            quality_score=0.7,
                        )
                        total_transcripts += 1

                    if not args.skip_comments:
                        comments = fetch_top_comments(http_client, settings.youtube_api_key, vid, n=10)
                        for c in comments:
                            upsert_source(
                                db,
                                kind="youtube_comment",
                                url=f"{video_url}&lc={c['id']}",
                                title=f"Comment on: {v['title']}",
                                author=c.get("author"),
                                published_at=parse_iso(c.get("published_at")),
                                content_raw=c["text"],
                                content_clean=clean_text(c["text"]),
                                quality_score=min(1.0, 0.4 + c["likes"] / 500),
                            )
                            total_comments += 1

                polite_sleep(0.3)

    log(f"transcripts: {total_transcripts} · comments: {total_comments}", "ok")


if __name__ == "__main__":
    main()
