"""Rellena la fecha de subida de los vídeos servidos con su hora y su zona.

GSC (20-11-2026): «Falta el campo uploadDate» y «falta la zona horaria». Se servía la
fecha sola. Este script reúne los `youtube_id` de `related_videos` y de
`posts.video` / `posts.videos` (y los de las propuestas, que se copian al post), pide
su `snippet.publishedAt` REAL a la YouTube Data API (50 por llamada, 1 unidad cada
una) y lo guarda entero. Un vídeo que la API no devuelve (borrado o privado) se queda
como estaba y sale en el informe: no se le inventa hora.

    python -m scripts.seo.backfill_video_dates            # ensayo: imprime un JSON
    python -m scripts.seo.backfill_video_dates --apply    # escribe
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime

from app.db.models import ContentProposal, Post, RelatedVideo
from app.db.session import SessionLocal
from app.services.video_dates import published_at_de_youtube, tiene_hora_y_zona


def _videos_de(fila) -> list[dict]:
    """Los dicts de vídeo de un post o de una propuesta (`video` + `videos`)."""
    out = [fila.video] if isinstance(fila.video, dict) else []
    out += [v for v in (fila.videos or []) if isinstance(v, dict)]
    return [v for v in out if v.get("youtube_id")]


def pendientes(db) -> tuple[list[RelatedVideo], list, set[str]]:
    """(vídeos relacionados sin `published_at`, posts y propuestas con algún vídeo sin
    fecha completa, ids a consultar)."""
    relacionados = db.query(RelatedVideo).filter(RelatedVideo.published_at.is_(None)).all()
    ids = {v.youtube_id for v in relacionados}
    filas = []
    for modelo in (Post, ContentProposal):
        for fila in db.query(modelo).filter(
                modelo.video.isnot(None) | modelo.videos.isnot(None)).all():
            faltan = [v["youtube_id"] for v in _videos_de(fila)
                      if not tiene_hora_y_zona(v.get("upload_date"))]
            if faltan:
                filas.append(fila)
                ids.update(faltan)
    return relacionados, filas, ids


def con_fecha(video: dict, fechas: dict[str, str]) -> dict:
    """El mismo dict con `upload_date` completo si la API lo ha dado."""
    nueva = fechas.get(video.get("youtube_id") or "")
    if nueva and not tiene_hora_y_zona(video.get("upload_date")):
        return {**video, "upload_date": nueva}
    return video


def aplicar(relacionados, filas, fechas: dict[str, str]) -> dict:
    """Escribe en los objetos (sin commit) y devuelve el recuento."""
    n_rel = 0
    for v in relacionados:
        if v.youtube_id in fechas:
            v.published_at = datetime.fromisoformat(fechas[v.youtube_id].replace("Z", "+00:00"))
            n_rel += 1
    n_filas = 0
    for fila in filas:
        antes = (fila.video, fila.videos)
        # JSONB: se reasigna un objeto nuevo, o SQLAlchemy no ve el cambio.
        if isinstance(fila.video, dict):
            fila.video = con_fecha(fila.video, fechas)
        if fila.videos:
            fila.videos = [con_fecha(v, fechas) if isinstance(v, dict) else v
                           for v in fila.videos]
        n_filas += (fila.video, fila.videos) != antes
    return {"related_videos": n_rel, "posts_y_propuestas": n_filas}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Escribe. Sin él, solo informa.")
    args = ap.parse_args()

    with SessionLocal() as db:
        relacionados, filas, ids = pendientes(db)
        fechas = published_at_de_youtube(sorted(ids)) if ids else {}
        informe = {
            "a_consultar": len(ids),
            "con_fecha_en_youtube": len(fechas),
            "sin_respuesta_de_youtube": sorted(ids - fechas.keys()),
            "fechas": fechas,
            "cambios": aplicar(relacionados, filas, fechas),
            "aplicado": bool(args.apply),
        }
        if args.apply:
            db.commit()
        else:
            db.rollback()
    print(json.dumps(informe, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
