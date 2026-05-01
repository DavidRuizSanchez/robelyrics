"""Fase 1 — Ingesta de letras desde Genius.

Para cada disco en `data/discography.yaml`:
  1. Buscar el álbum en Genius (lyricsgenius)
  2. Para cada track: descargar lyrics, limpiar headers/footers
  3. Segmentar en líneas y stanzas
  4. Generar chunks de 4 líneas con solape de 1 (para vector search)
  5. Upsert en `songs`, `lines`, `chunks` (idempotente por genius_id)

Idempotencia:
  - Songs por (album_id, slug) → ON CONFLICT UPDATE
  - Lines / Chunks: DELETE WHERE song_id=X + reinsert (simpler que diff)

Ejecución:
  docker compose exec api python -m scripts.ingest
  docker compose exec api python -m scripts.ingest --artist robe --album-slug salir
"""
from __future__ import annotations

import argparse
import re

from slugify import slugify
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import Album, Artist, Chunk, Line, Song
from scripts.research.common import (
    clean_text,
    get_session,
    load_discography,
    log,
    polite_sleep,
)
from scripts.sources.genius import FetchedTrack, fetch_album_tracks, make_client

CHUNK_LINES = 4
CHUNK_OVERLAP = 1


# --------------------------------------------------------------------------- #
# Limpieza de letras (heurísticas para output de lyricsgenius 3.x)
# --------------------------------------------------------------------------- #
# Header inicial: "Title" by Artist: \n[Letra de "Title"]
RE_HEADER_BY = re.compile(r'^\s*"[^"]+"\s+by\s+[^:]+:\s*\n', re.MULTILINE)
RE_LETRA_DE = re.compile(r"^\s*\[Letra de [^\]]+\]\s*\n", re.MULTILINE)
RE_LETRA = re.compile(r"^\s*\[Letra\]\s*\n", re.MULTILINE)
# Section headers: [Verso 1], [Estribillo], [Coro], [Solo], [Puente], [Outro]...
RE_SECTION = re.compile(r"^\s*\[[^\]]+\]\s*$", re.MULTILINE)
# Footer Genius: dígitos + "Embed" pegado, posiblemente "You might also like"
RE_EMBED = re.compile(r"\d*\s*Embed\s*$", re.MULTILINE)
RE_YOU_MIGHT = re.compile(r"You might also like\s*", re.IGNORECASE)
# Líneas spam: "X Contributors", "Translations*", "Read More", etc.
RE_CONTRIBUTORS = re.compile(r"^\s*\d+\s*Contributors?.*$", re.IGNORECASE | re.MULTILINE)
RE_TRANSLATIONS = re.compile(r"^\s*Translations.*$", re.IGNORECASE | re.MULTILINE)


def clean_lyrics(raw: str) -> str:
    """Limpia el texto de Genius dejando solo las líneas cantables."""
    if not raw:
        return ""
    text = raw

    text = RE_HEADER_BY.sub("", text)
    text = RE_LETRA_DE.sub("", text)
    text = RE_LETRA.sub("", text)
    text = RE_SECTION.sub("", text)
    text = RE_EMBED.sub("", text)
    text = RE_YOU_MIGHT.sub("", text)
    text = RE_CONTRIBUTORS.sub("", text)
    text = RE_TRANSLATIONS.sub("", text)

    # Normalizar: colapsa más de 2 saltos a 2 (separación de estrofas)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Quita espacios en cola de cada línea
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return text.strip()


# --------------------------------------------------------------------------- #
# Segmentación
# --------------------------------------------------------------------------- #
def segment_lines(clean: str) -> list[dict]:
    """Devuelve lista de dicts con line_index, stanza_index, text."""
    out: list[dict] = []
    stanza = 0
    line_idx = 0
    just_blank = False
    for raw_line in clean.split("\n"):
        line = raw_line.strip()
        if not line:
            if not just_blank:
                stanza += 1
                just_blank = True
            continue
        out.append({"line_index": line_idx, "stanza_index": stanza, "text": line})
        line_idx += 1
        just_blank = False
    return out


def make_chunks(lines: list[dict]) -> list[dict]:
    """Ventana deslizante de CHUNK_LINES líneas con solape CHUNK_OVERLAP."""
    if not lines:
        return []
    chunks: list[dict] = []
    step = max(1, CHUNK_LINES - CHUNK_OVERLAP)
    i = 0
    while i < len(lines):
        window = lines[i : i + CHUNK_LINES]
        if not window:
            break
        text = " / ".join(l["text"] for l in window)
        chunks.append(
            {
                "start_line_index": window[0]["line_index"],
                "end_line_index": window[-1]["line_index"],
                "text": text,
            }
        )
        if i + CHUNK_LINES >= len(lines):
            break
        i += step
    return chunks


# --------------------------------------------------------------------------- #
# Upsert
# --------------------------------------------------------------------------- #
def upsert_song_with_lyrics(db, album_id: int, track: FetchedTrack, track_index: int) -> tuple[int, int, int]:
    """Inserta o actualiza una canción + sus lines + chunks. Devuelve (song_id, n_lines, n_chunks)."""
    raw = track.raw_lyrics or ""
    clean = clean_lyrics(raw)
    title = track.title.strip()
    slug = slugify(title)[:240] or f"track-{track_index}"

    song_stmt = (
        pg_insert(Song)
        .values(
            album_id=album_id,
            track_number=track.track_number,
            title=title,
            slug=slug,
            lyrics_raw=raw,
            lyrics_clean=clean,
            genius_id=track.genius_id,
            genius_url=track.genius_url,
        )
        .on_conflict_do_update(
            constraint="uq_songs_album_slug",
            set_={
                "track_number": track.track_number,
                "title": title,
                "lyrics_raw": raw,
                "lyrics_clean": clean,
                "genius_id": track.genius_id,
                "genius_url": track.genius_url,
            },
        )
        .returning(Song.id)
    )
    song_id = db.execute(song_stmt).scalar_one()

    # Reset lines/chunks de esta canción (más simple que diff)
    db.query(Line).filter(Line.song_id == song_id).delete()
    db.query(Chunk).filter(Chunk.song_id == song_id).delete()

    line_rows = segment_lines(clean)
    if line_rows:
        db.execute(Line.__table__.insert(), [{"song_id": song_id, **lr} for lr in line_rows])

    chunk_rows = make_chunks(line_rows)
    if chunk_rows:
        db.execute(Chunk.__table__.insert(), [{"song_id": song_id, **cr} for cr in chunk_rows])

    return song_id, len(line_rows), len(chunk_rows)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artist", action="append", help="Filtra por slug (extremoduro|robe)")
    parser.add_argument("--album-slug", action="append", help="Solo procesa estos slugs de álbum")
    parser.add_argument("--limit-albums", type=int, default=None)
    args = parser.parse_args()

    data = load_discography()
    artists = data.get("artists", [])
    if args.artist:
        artists = [a for a in artists if a["slug"] in args.artist]

    g = make_client()
    total_songs = 0
    total_lines = 0
    total_chunks = 0
    skipped: list[str] = []

    for artist in artists:
        artist_name = artist["name"]
        artist_slug = artist["slug"]
        albums = artist.get("albums", [])
        if args.album_slug:
            albums = [a for a in albums if a["slug"] in args.album_slug]
        if args.limit_albums:
            albums = albums[: args.limit_albums]

        for alb in albums:
            with get_session() as db:
                # Resolver IDs en BD (artists+albums ya sembrados por seed_catalog)
                artist_obj = db.query(Artist).filter(Artist.slug == artist_slug).one_or_none()
                if artist_obj is None:
                    log(f"artista {artist_slug} no en BD — ¿ejecutaste seed_catalog?", "err")
                    return
                album_obj = (
                    db.query(Album)
                    .filter(Album.artist_id == artist_obj.id, Album.slug == alb["slug"])
                    .one_or_none()
                )
                if album_obj is None:
                    log(f"album {alb['slug']} no en BD — ¿ejecutaste seed_catalog?", "err")
                    return

                log(f"album · {alb['title']}")
                tracks = fetch_album_tracks(g, alb["title"], artist_name)
                if tracks is None:
                    log(f"  no encontrado en Genius", "warn")
                    skipped.append(f"{artist_slug}/{alb['slug']}")
                    continue

                log(f"  {len(tracks)} tracks")
                for i, tr in enumerate(tracks):
                    if not tr.title:
                        continue
                    if not tr.raw_lyrics or len(tr.raw_lyrics) < 50:
                        log(f"    skip '{tr.title}' (sin lyrics)", "warn")
                        continue
                    try:
                        sid, n_lines, n_chunks = upsert_song_with_lyrics(db, album_obj.id, tr, i)
                    except Exception as e:  # noqa: BLE001
                        log(f"    error '{tr.title}': {type(e).__name__}: {e}", "err")
                        continue
                    log(f"    {tr.title} · {n_lines} líneas / {n_chunks} chunks")
                    total_songs += 1
                    total_lines += n_lines
                    total_chunks += n_chunks

                polite_sleep(1.0)

    log(f"songs: {total_songs} · lines: {total_lines} · chunks: {total_chunks}", "ok")
    if skipped:
        log(f"álbumes saltados: {', '.join(skipped)}", "warn")


if __name__ == "__main__":
    main()
