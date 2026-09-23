"""Transcribe un concierto del catálogo para poder elegir momentos dentro.

CORRE EN LA MÁQUINA LOCAL: yt-dlp desde la IP del servidor recibe un bloqueo de
YouTube (lo mismo que el daemon de clips y el de transcripciones).

El `kind` es `live_transcript` a propósito y no `youtube_transcript`: una
transcripción de directo está garbleada (Whisper sobre música y aplausos) y NO
debe citarse nunca. `corpus_for_queries._ATRIBUCION` no tiene entrada para este
kind, así que la guarda que ya existe la descarta sola: «sin entrada aquí, no se
cita». Sirve para SABER QUÉ SUENA Y CUÁNDO, no para afirmar lo que se oye.

Uso:
    python -m scripts.instagram.transcribir_concierto --listar
    python -m scripts.instagram.transcribir_concierto --id CXADUCBLJII
    python -m scripts.instagram.transcribir_concierto --id X --minutos 20
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import tempfile

from sqlalchemy import select

from app.db.models import SourceSegment, VideoAsset
from app.db.session import SessionLocal
from app.services.instagram import video_clips
from scripts.research.common import clean_text, guardar_segmentos, upsert_source

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("concierto")

KIND = "live_transcript"
COSTE_POR_MINUTO = 0.006
# Whisper no admite más de 25 MB por fichero. A 16 kHz mono y calidad 9 son de
# sobra unos 40 minutos; por encima habría que trocear con offsets, y para
# elegir un momento no hace falta el bolo entero.
MAX_MINUTOS = 35


def _descargar_audio(url: str, minutos: int, destino: str) -> None:
    import yt_dlp

    with tempfile.TemporaryDirectory() as tmp:
        op = {
            # m4a por delante: es un contenedor que ffmpeg abre sin discusión.
            # OJO con la causa: el concierto de Las Ventas 1997 falló con
            # «ffmpeg exited with code 8» y al reintentarlo funcionó con las dos
            # selecciones de formato, la vieja y esta. O sea que aquel fallo era
            # INTERMITENTE (lado de YouTube), no del formato. Esto no lo arregla;
            # solo quita una variable de en medio cuando vuelva a pasar.
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
            "outtmpl": os.path.join(tmp, "a.%(ext)s"),
            "quiet": True, "noprogress": True, "no_warnings": True,
            "download_ranges": yt_dlp.utils.download_range_func(
                None, [(0, minutos * 60)]),
            "force_keyframes_at_cuts": True,
            **video_clips.runtime_js_para_ytdlp(),
        }
        with yt_dlp.YoutubeDL(op) as ydl:
            ydl.extract_info(url, download=True)
        ficheros = [f for f in os.listdir(tmp) if f.startswith("a.")]
        if not ficheros:
            raise RuntimeError("yt-dlp no dejó audio")
        crudo = os.path.join(tmp, max(
            ficheros, key=lambda f: os.path.getsize(os.path.join(tmp, f))))
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", crudo,
             "-ar", "16000", "-ac", "1", "-q:a", "9", destino],
            check=True,
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--id", help="youtube_id del concierto")
    ap.add_argument("--minutos", type=int, default=MAX_MINUTOS)
    ap.add_argument("--listar", action="store_true")
    args = ap.parse_args()

    with SessionLocal() as db:
        if args.listar:
            filas = db.execute(
                select(VideoAsset)
                .where(VideoAsset.kind == "live_fan", VideoAsset.vetado.is_(False))
                .order_by(VideoAsset.event_date.desc().nullslast())
            ).scalars().all()
            hechos = {
                s for (s,) in db.execute(select(SourceSegment.source_id).distinct()).all()
            }
            for a in filas:
                marca = "✓" if a.source_id in hechos else " "
                donde = a.event_place or "—"
                cuando = a.event_date or "—"
                logger.info(" %s %s | %-34s | %-12s | %s", marca, a.youtube_id,
                            str(donde)[:34], str(cuando), (a.title or "")[:46])
            return

        if not args.id:
            raise SystemExit("Hace falta --id (o --listar)")
        asset = db.execute(
            select(VideoAsset).where(VideoAsset.youtube_id == args.id)
        ).scalar_one_or_none()
        if asset is None:
            raise SystemExit(f"No está en el catálogo: {args.id}")
        if asset.vetado:
            raise SystemExit(f"Vetado: {asset.motivo_veto}")

        minutos = min(args.minutos, MAX_MINUTOS)
        logger.info("«%s» (%s) · %d min ≈ %.2f $", (asset.title or "")[:60],
                    asset.channel_title, minutos, minutos * COSTE_POR_MINUTO)

        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise SystemExit("Falta OPENAI_API_KEY")
        client = OpenAI(api_key=api_key)

        with tempfile.TemporaryDirectory() as tmp:
            audio = os.path.join(tmp, "concierto.mp3")
            _descargar_audio(asset.url, minutos, audio)
            tam = os.path.getsize(audio)
            logger.info("audio: %d KB", tam // 1024)
            with open(audio, "rb") as fh:
                resp = client.audio.transcriptions.create(
                    model="whisper-1", file=fh, language="es",
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
        segmentos = [
            {"start_s": s.start, "end_s": s.end, "text": s.text,
             "no_speech_prob": getattr(s, "no_speech_prob", None),
             "avg_logprob": getattr(s, "avg_logprob", None)}
            for s in (getattr(resp, "segments", None) or [])
        ]
        if not segmentos:
            raise SystemExit("Whisper no devolvió segmentos")
        texto = " ".join(s["text"].strip() for s in segmentos if s["text"]).strip()

        source_id = upsert_source(
            db, kind=KIND, url=asset.url, title=asset.title,
            author=asset.channel_title, published_at=None,
            content_raw=texto, content_clean=clean_text(texto),
            quality_score=0.3,   # baja a propósito: está garbleada, no se cita
            for_seo_only=False,
        )
        n = guardar_segmentos(db, source_id, segmentos)
        asset.source_id = source_id
        db.commit()
        sin_voz = sum(1 for s in segmentos if (s["no_speech_prob"] or 0) > 0.6)
        logger.info("%d tramos guardados (%d sin voz) · fuente #%d · coste ≈ %.2f $",
                    n, sin_voz, source_id, minutos * COSTE_POR_MINUTO)


if __name__ == "__main__":
    main()
