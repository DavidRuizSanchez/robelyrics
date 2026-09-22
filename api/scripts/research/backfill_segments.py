"""Recupera los TIEMPOS de las transcripciones que ya están en el corpus.

Whisper y los subtítulos de YouTube devuelven los tramos con `start`/`end`
desde siempre, y el pipeline los aplanaba a texto corrido antes de guardar. El
texto sirve para buscar y para el consultorio; los tiempos son lo único que
permite cortar un clip de vídeo sin que una persona lo vea entero y teclee
`desde` y `hasta`.

Se recuperan por el camino más barato primero:

  1. SUBTÍTULOS de YouTube (gratis). Si el vídeo los tiene, no se paga nada.
  2. WHISPER (~0,006 $/min) solo con `--whisper`, y solo para lo que no tenga
     subtítulos. Antes de gastar dice cuánto va a costar.

Corre en LOCAL: la descarga de audio necesita IP residencial (la del servidor
está bloqueada por el antibot de YouTube).

Uso:
    python -m scripts.research.backfill_segments --dry-run
    python -m scripts.research.backfill_segments                 # solo gratis
    python -m scripts.research.backfill_segments --whisper       # con coste
"""
from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from sqlalchemy import func, select

from app.db.models import InterpretationSource, SourceSegment
from app.db.session import SessionLocal
from scripts.research.common import guardar_segmentos
from scripts.transcribe_with_whisper import (
    WHISPER_MAX_BYTES,
    download_audio,
    extract_video_id,
    log,
    transcribe_audio,
)

# Los clips salen de entrevistas a Robe y de directos grabados por fans
# (decisión de David, 22-09-2026). Los análisis de terceros quedan fuera aunque
# sean los que más transcritos están.
KINDS_POR_DEFECTO = ("robe_interview",)
# Lo que cuesta Whisper por minuto de audio, para poder decirlo ANTES de gastar.
COSTE_POR_MINUTO = 0.006


def _sin_segmentos(db, kinds: tuple[str, ...]) -> list[InterpretationSource]:
    con_segmentos = select(SourceSegment.source_id).distinct()
    return list(db.execute(
        select(InterpretationSource)
        .where(
            InterpretationSource.kind.in_(kinds),
            InterpretationSource.id.not_in(con_segmentos),
            InterpretationSource.url.like("%youtu%"),
        )
        .order_by(InterpretationSource.id)
    ).scalars().all())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", action="append", default=None,
                    help=f"kinds a repescar (por defecto {KINDS_POR_DEFECTO})")
    ap.add_argument("--whisper", action="store_true",
                    help="pagar Whisper para lo que no tenga subtítulos")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    kinds = tuple(args.kind) if args.kind else KINDS_POR_DEFECTO

    with SessionLocal() as db:
        pendientes = _sin_segmentos(db, kinds)
        if args.limit:
            pendientes = pendientes[: args.limit]
        total_chars = sum(len(s.content_clean or "") for s in pendientes)
        log(f"Sin tiempos: {len(pendientes)} fuentes ({total_chars // 1000} k caracteres)")
        for s in pendientes:
            log(f"  · [{s.id}] {(s.title or s.url)[:80]}")
        if args.dry_run or not pendientes:
            return

        from scripts.research.fetch_youtube import fetch_transcript_segments

        gratis, para_whisper = 0, []
        for src in pendientes:
            vid = extract_video_id(src.url or "")
            if not vid:
                log(f"  [{src.id}] URL no parseable: {src.url}", "warn")
                continue
            segmentos = fetch_transcript_segments(vid)
            if segmentos:
                n = guardar_segmentos(db, src.id, segmentos)
                log(f"  [{src.id}] subtítulos: {n} tramos (0 €)")
                gratis += 1
            else:
                para_whisper.append((src, vid))

        log(f"Recuperados gratis: {gratis}. Sin subtítulos: {len(para_whisper)}")
        if not para_whisper:
            return
        if not args.whisper:
            log("Para los que no tienen subtítulos hace falta Whisper: "
                "vuelve a llamar con --whisper.")
            return

        # Antes de gastar, se dice cuánto. No se estima «a ojo»: la duración
        # sale del audio ya descargado, y por eso el aviso va dentro del bucle.
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise SystemExit("Falta OPENAI_API_KEY")
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        gastado_min = 0.0
        with tempfile.TemporaryDirectory() as tmp:
            for src, vid in para_whisper:
                audio = Path(tmp) / f"{vid}.mp3"
                if not download_audio(vid, audio, quality="9"):
                    continue
                if audio.stat().st_size > WHISPER_MAX_BYTES:
                    log(f"  [{src.id}] audio > 25 MB: saltado", "warn")
                    audio.unlink(missing_ok=True)
                    continue
                segs = transcribe_audio(client, audio)
                audio.unlink(missing_ok=True)
                if not segs:
                    continue
                minutos = (segs[-1].get("end") or 0) / 60
                gastado_min += minutos
                n = guardar_segmentos(db, src.id, [
                    {"start_s": s.get("start", 0.0), "end_s": s.get("end", 0.0),
                     "text": s.get("text", "")}
                    for s in segs
                ])
                log(f"  [{src.id}] whisper: {n} tramos, {minutos:.1f} min "
                    f"(~{minutos * COSTE_POR_MINUTO:.2f} $)")
        log(f"Whisper: {gastado_min:.1f} minutos ≈ "
            f"{gastado_min * COSTE_POR_MINUTO:.2f} $")

        con = db.execute(
            select(func.count()).select_from(
                select(SourceSegment.source_id).distinct().subquery()
            )
        ).scalar_one()
        log(f"Fuentes con tiempos en el corpus: {con}")


if __name__ == "__main__":
    main()
