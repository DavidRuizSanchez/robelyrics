"""Encola un audio suelto (un episodio de pódcast) para que el daemon lo transcriba.

Fase 4.3 del plan del corpus. Se pensó en leer los feeds RSS de los pódcast de
`data/sources.yaml`, pero medido el 25-10-2026 ninguno lo merece: el de Juancares
repite su canal de YouTube (ya en el corpus), La Gran Travesía son dos episodios
sueltos de iVoox y el de Fuego y Chinchetas está en Spotify, con DRM (yt-dlp se
niega). Lo que sí sirve es encolar un episodio por su URL, si yt-dlp lo baja.

Entra en `detected`: espera el clic en el panel como cualquier otro, y pasa por
el mismo tope semanal y el mismo presupuesto de Whisper.

Uso:
    python -m scripts.youtube.enqueue_audio --url URL --title "…" --author "La Gran Travesía"
    python -m scripts.youtube.enqueue_audio --url URL --title "…" --dry-run
"""
from __future__ import annotations

import argparse
import hashlib

from app.db.models import YouTubeIngestQueue
from scripts.research.common import get_session, log

KINDS = ("media_report", "entorno_interview", "robe_interview", "youtube_transcript")


def clave(url: str) -> str:
    """`video_id` sintético: la cola lo exige y es único con `target`."""
    return "audio:" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:24]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--author", default=None)
    ap.add_argument("--kind", choices=KINDS, default="media_report",
                    help="media_report (fondo) salvo que hable una voz de casa")
    ap.add_argument("--duration-s", type=float, default=None)
    ap.add_argument("--nota", default="audio suelto añadido a mano")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    vid = clave(args.url)
    with get_session() as db:
        ya = db.query(YouTubeIngestQueue).filter_by(video_id=vid, target="corpus").one_or_none()
        if ya:
            log(f"ya está en la cola (#{ya.id}, {ya.status})", "warn")
            return
        fila = YouTubeIngestQueue(
            video_id=vid, url=args.url, title=args.title, channel=args.author,
            author=args.author, target="corpus", kind=args.kind, status="detected",
            nivel="B" if args.kind == "media_report" else "C",
            motivos=[args.nota], descubierto_por="podcast", duration_s=args.duration_s)
        if args.dry_run:
            log(f"(dry-run) encolaría {vid} · {args.title} · {args.kind}")
            db.rollback()
            return
        db.add(fila)
        db.flush()
        log(f"encolado #{fila.id} · {args.title} (espera tu clic en el panel)", "ok")


if __name__ == "__main__":
    main()
