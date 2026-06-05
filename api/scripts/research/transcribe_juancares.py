"""Transcribe el canal de YouTube de Juancares con la Whisper API (uso LOCAL).

Pensado para correr en el contenedor api EN LOCAL (Mac, IP residencial): así
esquiva el antibot de YouTube que bloquea las descargas desde el datacenter de
producción (ver gotcha). Por cada vídeo:
  1. Descarga el mejor audio con yt-dlp.
  2. Lo trocea a 16 kHz mono y segmentos de 20 min con ffmpeg (<25 MB/chunk,
     límite de la Whisper API).
  3. Transcribe cada chunk (modelo whisper-1, español) y concatena.
  4. Hace upsert_source (kind=youtube_transcript) en la BD local.

La BD es la fuente de verdad y la base de la reanudabilidad (salta los vídeos
ya transcritos). Al terminar exporta TODO a un JSON (--out, en /tmp por defecto
porque data/ está montado read-only) que luego se saca con `docker cp` y se
versiona para importarlo en producción (donde no se puede descargar de YouTube).

Uso (dentro del contenedor api, en local):
    python -m scripts.research.transcribe_juancares --limit 1   # smoke test
    python -m scripts.research.transcribe_juancares             # canal completo
    python -m scripts.research.transcribe_juancares --export-only
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import httpx
from openai import OpenAI

from app.config import get_settings
from app.db.models import InterpretationSource
from scripts.research.common import (
    clean_text,
    get_session,
    log,
    polite_sleep,
    upsert_source,
)
from scripts.research.fetch_youtube import (
    get_uploads_playlist,
    list_videos,
    parse_iso,
    resolve_channel_id,
)

DEFAULT_OUT = "/tmp/juancares_transcripts.json"
HANDLE = "juancaraes"
AUTHOR = "Juancares"
CHUNK_SECONDS = 1200  # 20 min → 16 kHz mono mp3 ≈ pocos MB, muy por debajo de 25 MB


def _vid_from_url(url: str | None) -> str | None:
    m = re.search(r"[?&]v=([\w-]+)", url or "")
    return m.group(1) if m else None


def load_done_ids() -> set[str]:
    """video_id ya transcritos (en BD) → reanudable y robusto ante recreate."""
    with get_session() as db:
        rows = db.query(InterpretationSource.url).filter(
            InterpretationSource.kind == "youtube_transcript"
        ).all()
    return {vid for (u,) in rows if (vid := _vid_from_url(u))}


def export_json(out_path: str) -> int:
    """Vuelca todas las transcripciones de Juancares de la BD a un JSON
    (formato compatible con import_interview_transcripts: kind/url/title/...)."""
    with get_session() as db:
        rows = (
            db.query(InterpretationSource)
            .filter(
                InterpretationSource.kind == "youtube_transcript",
                InterpretationSource.author == AUTHOR,
            )
            .order_by(InterpretationSource.id)
            .all()
        )
        data = [
            {
                "kind": r.kind,
                "url": r.url,
                "title": r.title,
                "author": r.author,
                "content_clean": r.content_clean,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "video_id": _vid_from_url(r.url),
                "quality_score": r.quality_score,
            }
            for r in rows
        ]
    Path(out_path).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return len(data)


def download_audio(video_id: str, tmpdir: str) -> str | None:
    url = f"https://www.youtube.com/watch?v={video_id}"
    out_tmpl = os.path.join(tmpdir, "audio.%(ext)s")
    subprocess.run(
        ["yt-dlp", "-f", "bestaudio", "--no-playlist", "--quiet", "--no-warnings",
         "-o", out_tmpl, url],
        check=True,
    )
    files = [f for f in os.listdir(tmpdir) if f.startswith("audio.")]
    return os.path.join(tmpdir, files[0]) if files else None


def split_audio(src: str, tmpdir: str) -> list[str]:
    pattern = os.path.join(tmpdir, "chunk_%03d.mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1",
         "-f", "segment", "-segment_time", str(CHUNK_SECONDS),
         "-c:a", "libmp3lame", "-q:a", "9", pattern],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return sorted(
        os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.startswith("chunk_")
    )


def transcribe(client: OpenAI, chunks: list[str]) -> str:
    parts: list[str] = []
    for ch in chunks:
        with open(ch, "rb") as f:
            tr = client.audio.transcriptions.create(
                model="whisper-1", file=f, language="es",
            )
        parts.append((tr.text or "").strip())
    return " ".join(p for p in parts if p)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="Máx vídeos (smoke test).")
    ap.add_argument("--out", default=DEFAULT_OUT, help="Ruta del JSON exportado.")
    ap.add_argument("--export-only", action="store_true", help="Solo exportar BD→JSON.")
    args = ap.parse_args()

    if args.export_only:
        n = export_json(args.out)
        log(f"export: {n} transcripciones → {args.out}", "ok")
        return

    settings = get_settings()
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY") or settings.openai_api_key)

    done = load_done_ids()
    with httpx.Client(timeout=30) as c:
        cid = resolve_channel_id(c, settings.youtube_api_key, HANDLE)
        if not cid:
            log("canal no resuelto", "err")
            return
        pl = get_uploads_playlist(c, settings.youtube_api_key, cid)
        videos = list_videos(c, settings.youtube_api_key, pl)

    todo = [v for v in videos if v["video_id"] not in done]
    if args.limit:
        todo = todo[: args.limit]
    log(f"{len(videos)} vídeos en el canal · {len(done)} ya hechos · {len(todo)} por transcribir")

    n_ok = n_fail = 0
    for i, v in enumerate(todo, 1):
        vid = v["video_id"]
        try:
            with tempfile.TemporaryDirectory() as td:
                audio = download_audio(vid, td)
                if not audio:
                    raise RuntimeError("yt-dlp no devolvió audio")
                chunks = split_audio(audio, td)
                text = clean_text(transcribe(client, chunks))
            if len(text) < 100:
                raise RuntimeError("transcripción demasiado corta")
            url = f"https://www.youtube.com/watch?v={vid}"
            with get_session() as db:
                upsert_source(
                    db, kind="youtube_transcript", url=url, title=v["title"],
                    author=AUTHOR, published_at=parse_iso(v["published_at"]),
                    content_raw=text, content_clean=text, quality_score=0.7,
                )
            n_ok += 1
            log(f"[{i}/{len(todo)}] ✓ {vid} · {len(text)} chars · {(v['title'] or '')[:55]}", "ok")
        except Exception as e:  # noqa: BLE001
            n_fail += 1
            log(f"[{i}/{len(todo)}] ✗ {vid}: {type(e).__name__}: {e}", "warn")
        polite_sleep(0.5)

    total = export_json(args.out)
    log(f"Hecho: {n_ok} OK · {n_fail} fallos · {total} transcripciones en BD · JSON → {args.out}", "ok")


if __name__ == "__main__":
    main()
