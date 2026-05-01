"""Wrapper sobre lyricsgenius adaptado a la API real (3.x).

La librería tiene quirks (atributos vía to_dict, tracks como tuplas) que
encapsulamos aquí para que el resto del código no se ensucie.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lyricsgenius import Genius

from app.config import get_settings


@dataclass
class FetchedTrack:
    track_number: int | None
    genius_id: int | None
    genius_url: str | None
    title: str
    raw_lyrics: str | None


def make_client() -> Genius:
    settings = get_settings()
    if not settings.genius_token:
        raise RuntimeError("GENIUS_TOKEN no configurado")
    return Genius(
        settings.genius_token,
        timeout=20,
        sleep_time=1.0,
        retries=3,
        skip_non_songs=True,
        excluded_terms=["(Remix)", "(Live)", "(Demo)"],
        remove_section_headers=False,  # los limpiamos nosotros para mantener control
    )


def _song_attrs(song: Any) -> dict[str, Any]:
    """lyricsgenius 3.x: muchos campos solo accesibles vía to_dict()."""
    if hasattr(song, "to_dict"):
        return song.to_dict()
    return {}


def fetch_album_tracks(g: Genius, album_title: str, artist_name: str) -> list[FetchedTrack] | None:
    """Devuelve la lista de tracks con sus letras, o None si no se encuentra el álbum."""
    g_album = g.search_album(album_title, artist_name)
    if g_album is None:
        return None

    out: list[FetchedTrack] = []
    for tr in g_album.tracks or []:
        # Estructura real: (track_number, Song)
        if isinstance(tr, tuple) and len(tr) == 2:
            track_no, song = tr
        else:
            track_no = getattr(tr, "number", None)
            song = getattr(tr, "song", None)

        if song is None:
            continue
        attrs = _song_attrs(song)
        out.append(
            FetchedTrack(
                track_number=track_no if isinstance(track_no, int) else None,
                genius_id=attrs.get("id"),
                genius_url=attrs.get("url") or getattr(song, "url", None),
                title=attrs.get("title") or getattr(song, "title", "") or "",
                raw_lyrics=getattr(song, "lyrics", None),
            )
        )
    return out
