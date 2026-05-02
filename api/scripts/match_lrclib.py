"""Asigna `lines.start_seconds` a cada canción usando lrclib.net (gratis, sin auth).

Para cada Song con letra en BD:
  1. GET https://lrclib.net/api/get?artist_name=...&track_name=...
  2. Si la respuesta trae `syncedLyrics` (formato LRC con timestamps por línea):
     - Parsea el LRC
     - Empareja líneas LRC con `Line.text` de la canción usando
       `difflib.SequenceMatcher` con avance monotónico (greedy two-pointer)
     - Hace UPDATE bulk de `Line.start_seconds`

Idempotente. Si una canción ya tiene timestamps, los reescribe (--force) o
los respeta (--skip-if-set, default).

Ejecución:
  docker compose exec api python -m scripts.match_lrclib
"""
from __future__ import annotations

import argparse
import difflib
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

import httpx
from sqlalchemy import update

from app.db.models import Line, Song
from scripts.research.common import get_session, log, polite_sleep

LRCLIB_URL = "https://lrclib.net/api/get"
HEADERS = {"User-Agent": "RobeLyrics/0.1 (personal use)"}
SIMILARITY_THRESHOLD = 0.55


@dataclass
class LrcEntry:
    start_sec: int  # int (segundos enteros, basta para timestamp YouTube)
    text: str


# --------------------------------------------------------------------------- #
# Parser LRC
# --------------------------------------------------------------------------- #
LRC_TIMESTAMP = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]")


def parse_lrc(lrc: str) -> list[LrcEntry]:
    """Parsea el formato LRC. Una línea con varios `[mm:ss.xx]` produce varias entradas."""
    out: list[LrcEntry] = []
    for raw in lrc.split("\n"):
        # Saltar metadatos tipo [ar:Artist] [ti:Title] [length:...]
        if raw.startswith("[") and ":" not in raw[1:6]:
            continue
        timestamps: list[int] = []
        idx = 0
        while True:
            m = LRC_TIMESTAMP.match(raw, idx)
            if not m:
                break
            mm = int(m.group(1))
            ss = int(m.group(2))
            timestamps.append(mm * 60 + ss)
            idx = m.end()
        text = raw[idx:].strip()
        if not text or not timestamps:
            continue
        for ts in timestamps:
            out.append(LrcEntry(start_sec=ts, text=text))
    out.sort(key=lambda e: e.start_sec)
    return out


# --------------------------------------------------------------------------- #
# Matching de líneas LRC ↔ Line.text
# --------------------------------------------------------------------------- #
def normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def assign_timestamps(
    db_lines: list[Line],
    lrc_entries: list[LrcEntry],
) -> dict[int, int]:
    """Devuelve {line_id: start_seconds} matcheando posicionalmente con difflib.

    Two-pointer greedy: para cada Line BD en orden, busca la mejor LRC entry
    en una ventana hacia adelante desde la última asignación.
    """
    out: dict[int, int] = {}
    last_idx = -1  # índice usado en lrc_entries
    WINDOW_AHEAD = 6  # cuánto mirar hacia adelante en el LRC

    for db_line in db_lines:
        start = last_idx + 1
        end = min(start + WINDOW_AHEAD, len(lrc_entries))
        if start >= len(lrc_entries):
            break
        best_i = None
        best_sim = SIMILARITY_THRESHOLD
        for i in range(start, end):
            sim = similarity(db_line.text, lrc_entries[i].text)
            if sim > best_sim:
                best_sim = sim
                best_i = i
        if best_i is not None:
            out[db_line.id] = lrc_entries[best_i].start_sec
            last_idx = best_i
    return out


# --------------------------------------------------------------------------- #
# Llamada a lrclib
# --------------------------------------------------------------------------- #
def fetch_lrc(client: httpx.Client, artist: str, title: str) -> str | None:
    """Devuelve `syncedLyrics` raw o None si la API no la tiene."""
    try:
        r = client.get(
            LRCLIB_URL,
            params={"artist_name": artist, "track_name": title},
            headers=HEADERS,
            follow_redirects=True,
        )
    except httpx.HTTPError:
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    sl = data.get("syncedLyrics") or ""
    return sl if sl.strip() else None


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Reescribir aunque la canción ya tenga timestamps")
    parser.add_argument("--song-slug", help="Procesar solo una canción (debug)")
    args = parser.parse_args()

    n_songs_total = 0
    n_songs_with_lrc = 0
    n_songs_matched = 0
    n_lines_assigned = 0

    with httpx.Client(timeout=15) as client:
        # Materializamos slugs para no tener objetos detached
        with get_session() as db:
            q = db.query(Song)
            if args.song_slug:
                q = q.filter(Song.slug == args.song_slug)
            song_data = [
                (s.id, s.title, s.album.artist.name, s.slug)
                for s in q.all()
            ]
        log(f"canciones a procesar: {len(song_data)}")

        for song_id, title, artist_name, slug in song_data:
            n_songs_total += 1

            # Skip si ya tiene timestamps (a menos que --force)
            if not args.force:
                with get_session() as db:
                    has_ts = db.query(Line.id).filter(
                        Line.song_id == song_id,
                        Line.start_seconds.isnot(None),
                    ).first()
                    if has_ts:
                        continue

            lrc_text = fetch_lrc(client, artist_name, title)
            polite_sleep(0.3)
            if not lrc_text:
                continue
            n_songs_with_lrc += 1

            lrc_entries = parse_lrc(lrc_text)
            if not lrc_entries:
                continue

            # Cargar lines + ejecutar match en un único with
            with get_session() as db:
                db_lines = (
                    db.query(Line)
                    .filter(Line.song_id == song_id)
                    .order_by(Line.line_index)
                    .all()
                )
                if not db_lines:
                    continue
                assignments = assign_timestamps(db_lines, lrc_entries)
                if not assignments:
                    log(f"  ⚠ {title}: LRC tiene {len(lrc_entries)} líneas pero ningún match (umbral {SIMILARITY_THRESHOLD})", "warn")
                    continue
                # UPDATE bulk
                for line_id, sec in assignments.items():
                    db.execute(
                        update(Line).where(Line.id == line_id).values(start_seconds=sec)
                    )
                n_songs_matched += 1
                n_lines_assigned += len(assignments)
                pct = 100 * len(assignments) / len(db_lines)
                log(f"  ✓ {title}: {len(assignments)}/{len(db_lines)} líneas ({pct:.0f}%)")

    log(
        f"songs: {n_songs_total} · con LRC: {n_songs_with_lrc} · matcheadas: {n_songs_matched} · "
        f"líneas asignadas: {n_lines_assigned}",
        "ok",
    )


if __name__ == "__main__":
    main()
