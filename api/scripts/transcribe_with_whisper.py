"""Transcribe canciones SIN timestamps usando OpenAI Whisper sobre el audio
descargado de YouTube con yt-dlp. Alinea segmentos de Whisper con líneas
existentes en BD usando difflib (mismo matcher que match_lrclib.py).

Idempotente: solo procesa songs cuyas líneas no tienen `start_seconds`.

Modo `--source-mode`: en lugar de alinear con canciones, descarga + transcribe
entrevistas en vídeo (URL YouTube) y las guarda como InterpretationSource
(kind=youtube_transcript). Ideal para Robe en La Resistencia, Carne Cruda,
podcasts, documentales, etc. Lee `data/video_interviews.yaml`.

Coste: ~$0.006/min × 4 min/canción × 35 canciones ≈ $0.84.
Coste source-mode: ~$0,18-$0,36 por entrevista (30-60 min).

Ejecución:
  docker compose exec api python -m scripts.transcribe_with_whisper
  docker compose exec api python -m scripts.transcribe_with_whisper --song-slug ininteligible
  docker compose exec api python -m scripts.transcribe_with_whisper --source-mode
  docker compose exec api python -m scripts.transcribe_with_whisper --source-mode --interview-url https://...
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


# ─── Modo source: transcribir entrevistas en vídeo a InterpretationSource ── #
_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})")


def extract_video_id(url: str) -> str | None:
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    m = _VIDEO_ID_RE.search(url)
    return m.group(1) if m else None


def transcribe_to_source(
    client: OpenAI,
    url: str,
    title: str | None,
    author: str | None,
    tmpdir: Path,
) -> bool:
    """Descarga + transcribe + upserts como InterpretationSource. Devuelve True si OK."""
    from datetime import datetime, timezone

    from scripts.research.common import clean_text, upsert_source

    vid = extract_video_id(url)
    if not vid:
        log(f"  URL no parseable: {url}", "warn")
        return False

    audio_path = tmpdir / f"{vid}.mp3"
    if not download_audio(vid, audio_path):
        return False
    log(f"  audio: {audio_path.stat().st_size // 1024} KB")

    segments = transcribe_audio(client, audio_path)
    audio_path.unlink(missing_ok=True)
    if not segments:
        return False
    log(f"  whisper: {len(segments)} segmentos")

    full_text = " ".join(s["text"].strip() for s in segments if s.get("text")).strip()
    if len(full_text) < 200:
        log(f"  transcripción demasiado corta ({len(full_text)} chars)", "warn")
        return False

    with get_session() as db:
        upsert_source(
            db,
            kind="youtube_transcript",
            url=url,
            title=title,
            author=author,
            published_at=None,
            content_raw=full_text,
            content_clean=clean_text(full_text),
            quality_score=0.7,
            for_seo_only=False,  # entrevistas son material rico para destilador
        )
    return True


def _run_source_mode(
    client: OpenAI,
    interview_url: str | None,
    yaml_path: Path | None,
) -> None:
    import yaml as _yaml

    interviews: list[dict] = []
    if interview_url:
        interviews = [{"url": interview_url, "title": None, "author": None}]
    elif yaml_path and yaml_path.exists():
        data = _yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        interviews = data.get("interviews", []) or []
    else:
        log(f"sin --interview-url ni YAML válido en {yaml_path}", "err")
        return

    log(f"source-mode: {len(interviews)} entrevistas a procesar")
    n_ok = 0
    n_fail = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for i, e in enumerate(interviews, 1):
            log(f"[{i}/{len(interviews)}] {e.get('title') or e['url']}")
            try:
                if transcribe_to_source(
                    client, e["url"], e.get("title"), e.get("author"), tmp
                ):
                    n_ok += 1
                    log("  ✓ insertado/actualizado", "ok")
                else:
                    n_fail += 1
            except Exception as ex:  # noqa: BLE001
                log(f"  error inesperado: {ex}", "warn")
                n_fail += 1

    log(f"source-mode → ok: {n_ok} · fail: {n_fail}", "ok")


# ─── Main ──────────────────────────────────────────────────────────────── #
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--song-slug", help="Solo una canción (debug)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true",
                        help="Reescribir aunque ya tenga timestamps")
    parser.add_argument(
        "--source-mode", action="store_true",
        help="Modo entrevista: transcribe URLs de YouTube como InterpretationSource",
    )
    parser.add_argument(
        "--interview-url", default=None,
        help="(Con --source-mode) URL única; si no, lee data/video_interviews.yaml",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return
    client = OpenAI(api_key=settings.openai_api_key)

    if args.source_mode:
        from scripts.research.common import DATA_DIR
        _run_source_mode(
            client,
            interview_url=args.interview_url,
            yaml_path=DATA_DIR / "video_interviews.yaml",
        )
        return

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
