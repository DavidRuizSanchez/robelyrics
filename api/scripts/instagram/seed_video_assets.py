"""Cataloga de qué vídeos se puede sacar un clip, con el canal ya comprobado.

El veto de canales oficiales (`video_clips.canal_vetado`) solo podía aplicarse
DESPUÉS de descargar, porque el canal real solo lo sabía yt-dlp. Para un
preselector automático eso no vale: quemaría descargas e intentos en vídeos que
no se van a poder publicar nunca. Aquí el canal se resuelve antes, con la Data
API de YouTube (la misma que ya usa `match_youtube`), y el veredicto se guarda.

De dónde salen los candidatos (decisión de David, 22-09-2026):
  · `data/robe_interviews.yaml`, las entradas con `author_is_robe: true`.
  · `related_videos` con `kind` en (interview, live).
Los análisis de fans (Juancares, @tesonica) quedan FUERA aunque sean los que
más transcritos están.

Idempotente: se puede relanzar. Uso:
    python -m scripts.instagram.seed_video_assets --dry-run
    python -m scripts.instagram.seed_video_assets
"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml
from sqlalchemy import select

from app.db.models import InterpretationSource, RelatedVideo, VideoAsset
from app.db.session import SessionLocal
from app.services.instagram import video_clips
from scripts.match_youtube import parse_iso8601_duration

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("video-assets")

YT_API = "https://www.googleapis.com/youtube/v3"
DATA_DIRS = (Path("/app/data"), Path(__file__).resolve().parents[2] / "data")


def _data(nombre: str) -> Path | None:
    for d in DATA_DIRS:
        p = d / nombre
        if p.exists():
            return p
    return None


def _candidatos_yaml() -> list[dict]:
    """Entrevistas en las que HABLA Robe. El resto del fichero no vale."""
    ruta = _data("robe_interviews.yaml")
    if not ruta:
        return []
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    fuera = []
    for it in datos.get("interviews") or []:
        if it.get("medium") != "video" or not it.get("author_is_robe"):
            continue
        vid = video_clips.extraer_video_id(it.get("url") or "")
        if vid:
            fuera.append({"youtube_id": vid, "url": it["url"],
                          "title": it.get("title"), "kind": "interview"})
    return fuera


def _candidatos_related(db) -> list[dict]:
    filas = db.execute(
        select(RelatedVideo).where(RelatedVideo.kind.in_(("interview", "live")))
    ).scalars().all()
    return [
        {
            "youtube_id": v.youtube_id,
            "url": f"https://www.youtube.com/watch?v={v.youtube_id}",
            "title": v.title,
            # Un directo de `related_videos` es material de fan salvo que su
            # canal diga lo contrario, y eso lo decide el veto de más abajo.
            "kind": "live_fan" if v.kind == "live" else "interview",
        }
        for v in filas
    ]


def _metadatos(api_key: str, ids: list[str]) -> dict[str, dict]:
    """Canal y duración reales. 1 unidad de cuota por lote de 50."""
    out: dict[str, dict] = {}
    with httpx.Client(timeout=30) as client:
        for i in range(0, len(ids), 50):
            lote = ids[i : i + 50]
            r = client.get(f"{YT_API}/videos", params={
                "part": "snippet,contentDetails", "id": ",".join(lote),
                "key": api_key,
            })
            if r.status_code != 200:
                logger.warning("videos.list HTTP %s: %s", r.status_code, r.text[:160])
                continue
            for it in r.json().get("items", []):
                sn = it.get("snippet", {})
                cd = it.get("contentDetails", {})
                out[it["id"]] = {
                    "title": sn.get("title"),
                    "channel_title": sn.get("channelTitle"),
                    "channel_url": (
                        f"https://www.youtube.com/channel/{sn['channelId']}"
                        if sn.get("channelId") else None
                    ),
                    "duration_s": parse_iso8601_duration(cd.get("duration")),
                }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        raise SystemExit("Falta YOUTUBE_API_KEY")

    with SessionLocal() as db:
        candidatos = {c["youtube_id"]: c for c in _candidatos_yaml()}
        for c in _candidatos_related(db):
            candidatos.setdefault(c["youtube_id"], c)
        if not candidatos:
            logger.info("No hay candidatos.")
            return

        meta = _metadatos(api_key, list(candidatos))
        logger.info("Candidatos: %d · con metadatos: %d", len(candidatos), len(meta))

        # La transcripción de cada uno, si está en el corpus: es de donde salen
        # los tramos. Se casa por el id del vídeo dentro de la URL guardada.
        por_video: dict[str, int] = {}
        for src in db.execute(
            select(InterpretationSource).where(
                InterpretationSource.kind.in_(("robe_interview", "about_robe"))
            )
        ).scalars().all():
            vid = video_clips.extraer_video_id(src.url or "")
            if vid:
                por_video[vid] = src.id

        nuevos = vetados = 0
        for vid, cand in candidatos.items():
            m = meta.get(vid, {})
            canal = m.get("channel_title") or ""
            motivo = video_clips.canal_vetado(canal) if canal else None
            fila = db.execute(
                select(VideoAsset).where(VideoAsset.youtube_id == vid)
            ).scalar_one_or_none()
            if fila is None:
                fila = VideoAsset(youtube_id=vid, url=cand["url"], kind=cand["kind"])
                db.add(fila)
                nuevos += 1
            fila.title = m.get("title") or cand.get("title")
            fila.channel_title = canal or None
            fila.channel_url = m.get("channel_url")
            fila.duration_s = m.get("duration_s")
            fila.source_id = por_video.get(vid)
            # Sin metadatos NO se da por bueno: no saber de qué canal es un
            # vídeo es exactamente el caso que el veto tiene que atrapar.
            fila.vetado = bool(motivo) or not canal
            fila.motivo_veto = (
                f"canal vetado: «{canal}» casa con «{motivo}»" if motivo
                else (None if canal else "no se ha podido resolver el canal")
            )
            fila.checked_at = datetime.now(UTC)
            if fila.vetado:
                vetados += 1
                logger.info("  ✗ %s · %s", vid, fila.motivo_veto)
            else:
                logger.info("  ✓ %s · %s · %s · %s s · %s",
                            vid, (fila.title or "")[:50], canal, fila.duration_s,
                            "con transcripción" if fila.source_id else "SIN transcripción")

        if args.dry_run:
            db.rollback()
            logger.info("[dry-run] nada guardado")
            return
        db.commit()
        logger.info("Catálogo: %d candidatos, %d nuevos, %d vetados",
                    len(candidatos), nuevos, vetados)


if __name__ == "__main__":
    main()
