"""Descarga los clips de YouTube pendientes. CORRE EN LA MÁQUINA LOCAL.

Igual que `scripts/youtube/process_queue.py` y por el mismo motivo: yt-dlp desde
la IP del servidor recibe un bloqueo de YouTube, así que la descarga la hace la
Mac (IP residencial) y el resultado se sube a Cloudinary y se registra en
producción por HTTP.

Flujo por clip:
    GET  {PROD}/ingest/clips/pending
    POST {PROD}/ingest/clips/{id}/claim          → downloading
    yt-dlp (solo el tramo) → ffmpeg (9:16 + atribución quemada) → Cloudinary
    POST {PROD}/ingest/clips/{id}/complete       → ready
    (si algo falla)  POST .../fail               → failed, se reintenta

Uso:
    python -m scripts.instagram.process_clips
    python -m scripts.instagram.process_clips --dry-run    (solo lista)
"""
from __future__ import annotations

import argparse
import logging
import os
import tempfile

import httpx

from app.services.instagram import cloudinary_upload, video_clips

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("clips")

PROD = os.getenv("PROD_API_URL", "https://entreinteriores.com/api").rstrip("/")
KEY = os.getenv("INGEST_API_KEY", "")
TIMEOUT = 120.0
# Clip de UNA canción: cuánto audio se escucha para encontrar el estribillo.
# Una canción en directo cabe de sobra; Whisper cobra por minuto (0,006 $).
MINUTOS_A_ESCUCHAR = 6


class NoSeOyeElEstribillo(Exception):
    """No hay clip: lo que se oye no es el estribillo de esa canción. Es
    definitivo, reintentar no lo cambia."""


def _localizar_estribillo(clip: dict) -> dict:
    """Escucha el principio del vídeo y devuelve el tramo del estribillo.

    Localizar y verificar es el mismo paso (criterio de David, 09-10-2026): si
    no se oye el estribillo de ESA canción, no hay clip.
    """
    from openai import OpenAI

    from app.services.instagram.estribillo import localizar
    from scripts.instagram.transcribir_concierto import _descargar_audio

    if not clip.get("estribillo") or not clip.get("letra"):
        raise NoSeOyeElEstribillo(f"«{clip.get('cancion')}» no tiene estribillo identificado en la BD")
    with tempfile.TemporaryDirectory() as tmp:
        audio = os.path.join(tmp, "audio.mp3")
        _descargar_audio(clip["url"], MINUTOS_A_ESCUCHAR, audio)
        with open(audio, "rb") as fh:
            resp = OpenAI().audio.transcriptions.create(
                model="whisper-1", file=fh, language="es",
                response_format="verbose_json", timestamp_granularities=["segment"],
            )
    segmentos = [
        {"start": s.start, "end": s.end, "text": s.text,
         "no_speech_prob": getattr(s, "no_speech_prob", None)}
        for s in (getattr(resp, "segments", None) or [])
    ]
    tramo = localizar(segmentos, clip["estribillo"], clip["letra"])
    if tramo is None:
        raise NoSeOyeElEstribillo(
            f"en los primeros {MINUTOS_A_ESCUCHAR} min no se oye el estribillo de "
            f"«{clip.get('cancion')}» (o no es esa canción)")
    return {"start_s": tramo.start_s, "end_s": tramo.end_s,
            "verso": tramo.verso, "tramos_cancion": tramo.tramos_cancion}


def _cabeceras() -> dict:
    return {"Authorization": f"Bearer {KEY}"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    if not KEY:
        raise SystemExit("Falta INGEST_API_KEY en el entorno")

    with httpx.Client(timeout=TIMEOUT, headers=_cabeceras()) as client:
        resp = client.get(f"{PROD}/ingest/clips/pending")
        resp.raise_for_status()
        pendientes = resp.json()[: args.limit]

    if not pendientes:
        logger.info("No hay clips pendientes.")
        return

    logger.info("%d clip(s) por procesar", len(pendientes))
    for clip in pendientes:
        cid = clip["id"]
        etiqueta = f"#{cid} {clip['video_id']} ({clip['start_s']:.0f}-{clip['end_s']:.0f}s)"
        if args.dry_run:
            logger.info("  [DRY-RUN] %s · %s", etiqueta, clip["url"])
            continue

        try:
            with httpx.Client(timeout=TIMEOUT, headers=_cabeceras()) as client:
                client.post(f"{PROD}/ingest/clips/{cid}/claim").raise_for_status()

            localizado: dict = {}
            if clip.get("buscar_estribillo"):
                localizado = _localizar_estribillo(clip)
                logger.info("  %s estribillo en %.0f-%.0fs: «%s» (%d tramos casan)",
                            etiqueta, localizado["start_s"], localizado["end_s"],
                            localizado["verso"][:50], localizado["tramos_cancion"])

            with tempfile.TemporaryDirectory() as tmp:
                destino = os.path.join(tmp, f"clip_{cid}.mp4")
                meta = video_clips.descargar_y_recortar(
                    url=clip["url"],
                    start_s=localizado.get("start_s", clip["start_s"]),
                    end_s=localizado.get("end_s", clip["end_s"]),
                    canal=clip.get("channel_title") or "",
                    subtitulo=clip.get("subtitle"),
                    rotulo=clip.get("overlay"),
                    destino=destino,
                )
                logger.info(
                    "  %s descargado (%.1f MB, canal: %s)%s",
                    etiqueta, meta["size_mb"], meta["channel_title"],
                    "  ⚠ IMAGEN FIJA" if meta.get("imagen_fija") else "",
                )
                subido = cloudinary_upload.upload_video(destino)

            with httpx.Client(timeout=TIMEOUT, headers=_cabeceras()) as client:
                client.post(
                    f"{PROD}/ingest/clips/{cid}/complete",
                    json={
                        "url_cdn": subido["url"],
                        "cloudinary_public_id": subido["public_id"],
                        "duration_s": meta["duration_s"],
                        "video_title": meta["video_title"],
                        "channel_title": meta["channel_title"],
                        "channel_url": meta["channel_url"],
                        # Solo se sabe habiendo bajado el tramo: el servidor no
                        # puede comprobarlo porque YouTube le bloquea.
                        "imagen_fija": meta.get("imagen_fija"),
                        **localizado,
                    },
                ).raise_for_status()
            logger.info("  ✅ %s listo", etiqueta)

        except Exception as exc:  # noqa: BLE001
            permanente = isinstance(exc, NoSeOyeElEstribillo)
            logger.error("  ❌ %s %s: %s", etiqueta,
                         "descartado" if permanente else "falló", exc)
            try:
                with httpx.Client(timeout=30.0, headers=_cabeceras()) as client:
                    client.post(
                        f"{PROD}/ingest/clips/{cid}/fail",
                        json={"error": str(exc)[:1000], "permanente": permanente},
                    )
            except Exception:  # noqa: BLE001
                logger.warning("  (tampoco se pudo avisar del fallo)")


if __name__ == "__main__":
    main()
