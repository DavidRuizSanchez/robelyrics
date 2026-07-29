"""Daemon LOCAL (Mac, IP residencial): transcribe y empuja a prod los vídeos
aprobados en la cola de ingesta.

Corre en el contenedor api EN LOCAL (lo lanza launchd vía docker exec). Habla
SOLO con producción por HTTP — NO toca la BD local. Esquiva el antibot de
YouTube porque la descarga sale por la IP residencial de casa.

Por cada vídeo `approved` en prod:
  1. claim   → lo marca `processing` (evita que dos pasadas lo pisen).
  2. yt-dlp (bestaudio) → ffmpeg (16 kHz mono, segmentos 20 min) → Whisper (es).
  3. complete → POST de la transcripción; prod hace upsert_source (kind correcto).
  Si algo falla → fail (suma intento; se reintenta en la siguiente pasada).

Config (vars de entorno, ya en el .env del contenedor):
  PROD_API_URL    base de la API de prod (p.ej. https://entreinteriores.com/api)
  INGEST_API_KEY  bearer compartido con prod
  OPENAI_API_KEY  para Whisper

Uso:
    python -m scripts.youtube.process_queue
    python -m scripts.youtube.process_queue --max 3   # tope por pasada (smoke)
"""
from __future__ import annotations

import argparse
import logging
import os
import tempfile

import httpx
from openai import OpenAI

from app.config import get_settings
from scripts.research.common import clean_text
from scripts.research.transcribe_juancares import (
    audio_duration_s,
    download_audio,
    min_chars_for,
    split_audio,
    transcribe,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MIN_CHARS = 100  # tope del suelo; el real lo escala min_chars_for() con la duración


def _base_and_headers() -> tuple[str, dict]:
    settings = get_settings()
    base = os.environ.get("PROD_API_URL", settings.prod_api_url).rstrip("/")
    key = os.environ.get("INGEST_API_KEY", settings.ingest_api_key or "")
    if not key:
        raise SystemExit("INGEST_API_KEY no configurado: no puedo hablar con prod")
    return base, {"Authorization": f"Bearer {key}"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max", type=int, default=None, help="Tope de vídeos por pasada.")
    args = ap.parse_args()

    base, headers = _base_and_headers()
    settings = get_settings()
    openai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY") or settings.openai_api_key)

    with httpx.Client(timeout=60, headers=headers) as http:
        r = http.get(f"{base}/ingest/youtube/pending")
        r.raise_for_status()
        items = r.json()
        if args.max:
            items = items[: args.max]
        logger.info("%d vídeos aprobados pendientes", len(items))

        n_ok = n_fail = 0
        for it in items:
            item_id = it["id"]
            vid = it["video_id"]
            title = it.get("title") or vid
            try:
                claim = http.post(f"{base}/ingest/youtube/{item_id}/claim")
                if claim.status_code == 409:
                    # Otra pasada se lo llevó (el launchd dispara cada 15 min y una
                    # manual puede solaparse). No es un fallo nuestro y no se reporta
                    # como tal: se salta y ya.
                    logger.info("[·] %s lo está haciendo otra pasada: %s",
                                vid, claim.json().get("detail", "")[:60])
                    continue
                claim.raise_for_status()
                with tempfile.TemporaryDirectory() as td:
                    audio = download_audio(vid, td)
                    if not audio:
                        raise RuntimeError("yt-dlp no devolvió audio")
                    dur = audio_duration_s(audio)
                    chunks = split_audio(audio, td)
                    text = clean_text(transcribe(openai, chunks)) or ""
                floor = min_chars_for(dur, ceiling=MIN_CHARS)
                if len(text) < floor:
                    raise RuntimeError(
                        f"transcripción demasiado corta ({len(text)} chars < {floor} "
                        f"para {dur and round(dur)}s de audio)"
                    )
                resp = http.post(
                    f"{base}/ingest/youtube/{item_id}/complete",
                    json={"content_clean": text, "title": it.get("title")},
                )
                resp.raise_for_status()
                n_ok += 1
                logger.info("[✓] %s · %d chars · %s", vid, len(text), title[:55])
            except Exception as e:  # noqa: BLE001
                n_fail += 1
                msg = f"{type(e).__name__}: {e}"
                # Un 4xx de prod trae el motivo REAL en el cuerpo; sin esto, un
                # rechazo de validación se registraba como «422» a secas y había que
                # ir a leer el router para saber qué campo lo había tumbado.
                if isinstance(e, httpx.HTTPStatusError):
                    msg += f" · respuesta: {e.response.text[:300]}"
                logger.warning("[✗] %s: %s", vid, msg)
                try:
                    http.post(
                        f"{base}/ingest/youtube/{item_id}/fail",
                        json={"error": msg[:2000]},
                    )
                except Exception:  # noqa: BLE001
                    logger.warning("no pude reportar el fallo de %s a prod", vid)

    logger.info("Pasada terminada: %d OK · %d fallos", n_ok, n_fail)


if __name__ == "__main__":
    main()
