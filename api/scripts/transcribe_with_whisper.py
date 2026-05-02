"""Transcribe canciones SIN timestamps usando OpenAI Whisper sobre el audio
descargado de YouTube con yt-dlp. Alinea segmentos de Whisper con líneas
existentes en BD usando difflib (mismo matcher que match_lrclib.py).

Idempotente: solo procesa songs cuyas líneas no tienen `start_seconds`.

Coste: ~$0.006/min × 4 min/canción × 35 canciones ≈ $0.84.

Ejecución:
  docker compose exec api python -m scripts.transcribe_with_whisper
  docker compose exec api python -m scripts.transcribe_with_whisper --song-slug ininteligible
"""
from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

from openai import OpenAI
from sqlalchemy import update

from app.config import get_settings
from app.db.models import Line, Song
from scripts.research.common import get_session, log

SIMILARITY_THRESHOLD = 0.50  # más permisivo que LRC porque Whisper puede malinterpretar

# ─── normalización + matcher (copiado de match_lrclib.py) ────────────────── #
def normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()


# ─── descarga audio con yt-dlp ──────────────────────────────────────────── #
def download_audio(video_id: str, dest: Path) -> bool:
    """Descarga el audio del video como mp3. Devuelve True si OK."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        subprocess.run(
            [
                "yt-dlp",
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "5",  # ~96kbps, suficiente para Whisper
                "-o", str(dest),
                "--no-playlist",
                "--quiet",
                "--no-warnings",
                url,
            ],
            check=True,
            timeout=120,
            capture_output=True,
        )
        return dest.exists() and dest.stat().st_size > 0
    except subprocess.CalledProcessError as e:
        log(f"  yt-dlp falló: {e.stderr.decode()[:200] if e.stderr else e}", "warn")
        return False
    except subprocess.TimeoutExpired:
        log("  yt-dlp timeout (>120s)", "warn")
        return False


# ─── Whisper transcripción ─────────────────────────────────────────────── #
def transcribe_audio(client: OpenAI, audio_path: Path) -> list[dict] | None:
    """Llama a Whisper API. Devuelve lista de segmentos [{start, end, text}]."""
    try:
        with audio_path.open("rb") as f:
            resp = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
                language="es",
            )
    except Exception as e:  # noqa: BLE001
        log(f"  Whisper error: {type(e).__name__}: {e}", "warn")
        return None
    segments = getattr(resp, "segments", None) or []
    return [{"start": s.start, "end": s.end, "text": s.text} for s in segments]


# ─── alineamiento: segmentos Whisper → líneas BD ───────────────────────── #
def assign_timestamps(
    db_lines: list[Line],
    segments: list[dict],
) -> dict[int, int]:
    """Asigna start_seconds a cada line buscando el segmento Whisper más
    similar en una ventana hacia adelante (greedy two-pointer)."""
    out: dict[int, int] = {}
    last_idx = -1
    WINDOW = 8

    for db_line in db_lines:
        start = last_idx + 1
        end = min(start + WINDOW, len(segments))
        if start >= len(segments):
            break
        best_i = None
        best_sim = SIMILARITY_THRESHOLD
        for i in range(start, end):
            sim = similarity(db_line.text, segments[i]["text"])
            if sim > best_sim:
                best_sim = sim
                best_i = i
        if best_i is not None:
            out[db_line.id] = round(segments[best_i]["start"])
            last_idx = best_i
    return out


# ─── Main ──────────────────────────────────────────────────────────────── #
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--song-slug", help="Solo una canción (debug)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true",
                        help="Reescribir aunque ya tenga timestamps")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return
    client = OpenAI(api_key=settings.openai_api_key)

    # Materializar candidatos
    with get_session() as db:
        q = db.query(Song).filter(Song.youtube_id.isnot(None))
        if args.song_slug:
            q = q.filter(Song.slug == args.song_slug)
        songs_data = [(s.id, s.slug, s.title, s.youtube_id) for s in q.all()]

    # Filtrar las que ya tienen timestamps (a menos que --force)
    if not args.force:
        with get_session() as db:
            songs_with_ts = {
                row[0]
                for row in db.query(Line.song_id)
                .filter(Line.start_seconds.isnot(None))
                .distinct()
                .all()
            }
        songs_data = [s for s in songs_data if s[0] not in songs_with_ts]

    log(f"canciones a transcribir: {len(songs_data)}")
    if args.limit:
        songs_data = songs_data[: args.limit]

    n_done = 0
    n_failed = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for i, (song_id, slug, title, video_id) in enumerate(songs_data, 1):
            log(f"[{i}/{len(songs_data)}] {title} (yt:{video_id})")
            audio_path = tmp / f"{slug}.mp3"

            # 1. Descargar
            if not download_audio(video_id, audio_path):
                n_failed += 1
                continue
            log(f"  audio: {audio_path.stat().st_size // 1024} KB")

            # 2. Whisper
            segments = transcribe_audio(client, audio_path)
            audio_path.unlink(missing_ok=True)  # limpieza inmediata
            if not segments:
                n_failed += 1
                continue
            log(f"  whisper: {len(segments)} segmentos")

            # 3. Alinear con líneas en BD
            with get_session() as db:
                db_lines = (
                    db.query(Line)
                    .filter(Line.song_id == song_id)
                    .order_by(Line.line_index)
                    .all()
                )
                assignments = assign_timestamps(db_lines, segments)
                if not assignments:
                    log("  ⚠ sin matches sobre el threshold", "warn")
                    n_failed += 1
                    continue
                for line_id, sec in assignments.items():
                    db.execute(
                        update(Line)
                        .where(Line.id == line_id)
                        .values(start_seconds=sec)
                    )
                pct = 100 * len(assignments) / len(db_lines)
                log(f"  ✓ {len(assignments)}/{len(db_lines)} líneas ({pct:.0f}%)")
            n_done += 1

    log(f"transcritas: {n_done} · sin éxito: {n_failed}", "ok")


if __name__ == "__main__":
    main()
