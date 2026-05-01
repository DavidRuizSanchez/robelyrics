"""Descarga anotaciones de Genius para cada canción del corpus.

Las anotaciones en Genius son interpretaciones que han escrito otros fans
verificadas a fragmentos concretos de letras. Es la fuente más limpia y
estructurada que tenemos.

Ejecución: docker compose exec api python -m scripts.research.fetch_genius_annotations
"""
from __future__ import annotations

import argparse
from typing import Any

from lyricsgenius import Genius

from app.config import get_settings
from scripts.research.common import (
    clean_text,
    get_session,
    load_discography,
    log,
    polite_sleep,
    upsert_source,
)


def make_client() -> Genius:
    settings = get_settings()
    if not settings.genius_token:
        raise RuntimeError("GENIUS_TOKEN no está configurado")
    g = Genius(
        settings.genius_token,
        timeout=20,
        sleep_time=1.0,
        retries=3,
        skip_non_songs=True,
        excluded_terms=["(Remix)", "(Live)", "(Demo)"],
        remove_section_headers=False,
    )
    return g


def extract_referents(annotations_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Aplana la respuesta del endpoint /referents.

    Estructura real (lyricsgenius 3.x):
      { "referents": [
        {"id": 123, "fragment": "...", "url": "https://genius.com/...",
         "annotations": [{"id": 456, "body": {"plain": "..."},
                          "share_url": "...", "verified": false}]}
      ]}
    """
    out: list[dict[str, Any]] = []
    refs = (annotations_payload or {}).get("referents", []) or []
    for r in refs:
        fragment = r.get("fragment") or ""
        ref_url = r.get("url") or ""
        for ann in r.get("annotations") or []:
            plain = (ann.get("body") or {}).get("plain") or ""
            if not plain.strip():
                continue
            out.append(
                {
                    "annotation_id": ann.get("id"),
                    "url": ann.get("share_url") or ref_url or f"https://genius.com/annotations/{ann.get('id')}",
                    "fragment": fragment,
                    "body": plain,
                    "verified": ann.get("verified", False),
                }
            )
    return out


def fetch_for_song(g: Genius, song_id: int) -> list[dict[str, Any]]:
    """Llama al endpoint /referents?song_id=... vía el cliente lyricsgenius."""
    try:
        # lyricsgenius expone el método público referents() que internamente
        # hace GET /referents?song_id=ID
        payload = g.referents(song_id=song_id, per_page=50)
    except Exception as e:  # noqa: BLE001
        log(f"genius referents error song_id={song_id}: {type(e).__name__}: {e}", "warn")
        return []
    return extract_referents(payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artist", action="append", help="Filtra por slug (extremoduro|robe). Si se omite, ambos.")
    parser.add_argument("--album-slug", action="append", help="Solo procesa estos slugs de álbum.")
    parser.add_argument("--limit-albums", type=int, default=None, help="Procesar solo N discos (smoke test).")
    args = parser.parse_args()

    data = load_discography()
    artists = data.get("artists", [])
    if args.artist:
        artists = [a for a in artists if a["slug"] in args.artist]

    g = make_client()
    total_annotations = 0

    for artist in artists:
        artist_name = artist["name"]
        albums = artist.get("albums", [])
        if args.limit_albums:
            albums = albums[: args.limit_albums]

        if args.album_slug:
            albums = [a for a in albums if a["slug"] in args.album_slug]

        for alb in albums:
            # Una sesión por álbum: commit al cerrar el `with`. Si el script
            # crashea mid-album perdemos solo ese álbum, no todo lo anterior.
            with get_session() as db:
                title = alb["title"]
                log(f"buscando album '{title}' de {artist_name}...")
                try:
                    g_album = g.search_album(title, artist_name)
                except Exception as e:  # noqa: BLE001
                    log(f"  search_album falló: {type(e).__name__}: {e}", "warn")
                    continue

                if g_album is None:
                    log(f"  no encontrado en Genius", "warn")
                    continue

                tracks = g_album.tracks or []
                log(f"  {len(tracks)} tracks en Genius")

                for tr in tracks:
                    # lyricsgenius 3.x: tracks = [(track_number, Song), ...]
                    if isinstance(tr, tuple):
                        song = tr[1]
                    else:
                        song = getattr(tr, "song", None)
                    if song is None:
                        continue
                    song_dict = song.to_dict() if hasattr(song, "to_dict") else {}
                    song_id = song_dict.get("id")
                    annotation_count = song_dict.get("annotation_count", 0) or 0
                    if not song_id:
                        continue
                    if annotation_count == 0:
                        # Skip: no hay annotations, ahorramos llamada
                        continue
                    referents = fetch_for_song(g, song_id)
                    if not referents:
                        continue

                    for ref in referents:
                        body = clean_text(ref["body"])
                        fragment = clean_text(ref["fragment"]) or ""
                        if not body or len(body) < 30:
                            continue  # demasiado corto para ser útil
                        url = ref["url"] or f"https://genius.com/{song_id}-annotation"
                        title_str = f"{artist_name} — {song.title}: «{fragment[:80]}»"
                        # Quality score: mayor si está verificada
                        q = 0.9 if ref["verified"] else 0.5

                        upsert_source(
                            db,
                            kind="genius_annotation",
                            url=url,
                            title=title_str,
                            author="genius_fan",
                            content_raw=ref["body"],
                            content_clean=body,
                            quality_score=q,
                        )
                        total_annotations += 1

                    polite_sleep(0.5)

                polite_sleep(1.0)

    log(f"Total annotations upserted: {total_annotations}", "ok")


if __name__ == "__main__":
    main()
