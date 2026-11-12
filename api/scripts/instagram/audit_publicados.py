"""Auditoría de lo YA PUBLICADO en Instagram con las guardas de hoy.

Existe porque el 08-11-2026 un seguidor corrigió en público un clip («No es "La
Carrera", sino "Destrozares"») y al tirar del hilo salieron más: notas internas
publicadas, metatexto, versos de otra canción, un directo de Robe atribuido a
Extremoduro. El gate final evita que vuelva a salir; esto dice qué hay fuera.

Por cada post publicado:
  - el gate final (texto del proceso, metatexto, intérprete y títulos del clip);
  - en los clips de concierto, la canción REIDENTIFICADA con el consenso de
    `momentos.clasificar` sobre sus segmentos, frente a la que dice el título.

Propone una acción, nunca la ejecuta: NO borra, NO edita, NO despublica. No hay
camino para ello en el código y no conviene que lo haya. Lo hace una persona en
instagram.com. Por eso NO va al crontab (misma decisión que `audit_identidad`).

Uso:
    python -m scripts.instagram.audit_publicados [--csv /tmp/auditoria.csv]
"""
from __future__ import annotations

import argparse
import csv
import logging
import re
import sys

from sqlalchemy import func, select

from app.db.models import Album, InstagramQueueItem, Song, SourceSegment, VideoClip
from app.db.session import SessionLocal
from app.services.instagram import gate_final, graph_api, momentos

logging.basicConfig(level=logging.WARNING)

_TITULO_CLIP = re.compile(r"«([^»]+)»")


def _cancion_del_titulo(titulo: str) -> str | None:
    m = _TITULO_CLIP.search(titulo or "")
    return m.group(1) if m else None


def _frases_limpias(caption: str) -> str:
    """El caption sin las frases que el gate marca. Una PROPUESTA para editar en
    la app: quitar es seguro; reescribir no se hace aquí."""
    fuera = []
    for parrafo in (caption or "").split("\n"):
        frases = re.split(r"(?<=[.!?])\s+", parrafo)
        buenas = [f for f in frases if not gate_final.problemas_de_texto(f)]
        fuera.append(" ".join(buenas).strip())
    texto = "\n".join(fuera)
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def _reidentificar(db, clip: VideoClip, catalogo) -> tuple[str | None, str]:
    """Canción del tramo del clip con el consenso de hoy, y la evidencia."""
    from app.db.models import InterpretationSource

    fuente = db.execute(
        select(InterpretationSource).where(InterpretationSource.url.like(f"%{clip.video_id}%"))
    ).scalars().first()
    if fuente is None:
        return None, "sin transcripción del concierto"
    segs = db.execute(
        select(SourceSegment)
        .where(SourceSegment.source_id == fuente.id,
               SourceSegment.end_s >= clip.start_s - 150,
               SourceSegment.start_s <= clip.end_s + 150)
        .order_by(SourceSegment.idx)
    ).scalars().all()
    if not segs:
        return None, "sin segmentos con tiempos"
    tramo = [m for m in momentos.clasificar(segs, catalogo)
             if m.start_s < clip.end_s and m.end_s > clip.start_s]
    con_cancion = [m for m in tramo if m.cancion]
    if not con_cancion:
        return None, "el consenso no identifica ninguna canción en el tramo"
    m = max(con_cancion, key=lambda x: min(x.end_s, clip.end_s) - max(x.start_s, clip.start_s))
    return m.cancion, f"{m.tipo} · {m.start_s:.0f}-{m.end_s:.0f}s · {'; '.join(m.motivos)}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", help="ruta del CSV de salida")
    args = ap.parse_args()

    filas = []
    with SessionLocal() as db:
        catalogo = momentos.cargar_catalogo(db)
        canciones_y_discos = set(db.execute(select(Song.title)).scalars().all())
        canciones_y_discos |= set(db.execute(select(Album.title)).scalars().all())
        items = db.execute(
            select(InstagramQueueItem).where(InstagramQueueItem.status == "published")
            .order_by(InstagramQueueItem.id)
        ).scalars().all()
        for it in items:
            clip = db.execute(
                select(VideoClip).where(VideoClip.queue_item_id == it.id)
            ).scalars().first()
            if clip is not None and clip.status == "retired":
                continue        # ya retirado (el #504, por ejemplo)
            problemas: list[str] = []
            evidencia = ""
            accion = ""
            ctx = None
            if clip is not None:
                permitidos: set[str] = set()
                titulo_cancion = _cancion_del_titulo(it.title)
                if titulo_cancion:
                    s = db.execute(select(Song).where(func.lower(Song.title) == titulo_cancion.lower())).scalars().first()
                    if s is not None:
                        permitidos.add(s.title)
                        if s.album is not None:
                            permitidos.add(s.album.title)
                ctx = {
                    "interprete": gate_final.interprete_del_video(
                        clip.video_title or "", clip.channel_title or ""),
                    "titulos_permitidos": permitidos,
                    "titulos_catalogo": canciones_y_discos,
                }
                # Solo los clips de concierto completo: los de una canción
                # (`song_id` puesto) ya se verificaron escuchando el audio.
                if titulo_cancion and clip.song_id is None:
                    real, evidencia = _reidentificar(db, clip, catalogo)
                    if real is None:
                        problemas.append(
                            f"canción NO VERIFICABLE: el título dice «{titulo_cancion}» y el "
                            f"consenso de hoy no la confirma ({evidencia})")
                        accion = "REVISAR viendo el clip (si no es esa canción, BORRAR)"
                    elif gate_final._norm_titulo(real) != gate_final._norm_titulo(titulo_cancion):
                        problemas.append(
                            f"canción mal identificada: el título dice «{titulo_cancion}» y el "
                            f"tramo es «{real}»")
                        accion = "BORRAR (el título está quemado en el vídeo)"
            v = gate_final.revisar(
                caption=it.caption or "",
                rotulo="\n".join(x for x in ((clip.overlay if clip else None),
                                              (clip.subtitle if clip else None)) if x),
                clip=ctx,
            )
            problemas += v.bloqueos
            if not problemas:
                continue
            if not accion:
                rotulo_mal = any(p.startswith("rótulo") for p in v.bloqueos)
                accion = ("BORRAR (el error está quemado en el vídeo)" if rotulo_mal
                          else "EDITAR el caption en la app (propuesta abajo)")
            filas.append({
                "id": it.id,
                "publicado": it.published_at.date().isoformat() if it.published_at else "",
                "tipo": it.content_type,
                "titulo": it.title,
                "enlace": graph_api.permalink(it.ig_media_id) if it.ig_media_id else "",
                "problemas": " | ".join(problemas),
                "evidencia_clip": evidencia,
                "accion": accion,
                "caption_propuesto": "" if accion.startswith("BORRAR") else _frases_limpias(it.caption),
            })

    for f in filas:
        print(f"\n#{f['id']} · {f['publicado']} · {f['tipo']} · {f['titulo'][:70]}")
        print(f"  enlace:    {f['enlace'] or '—'}")
        print(f"  problemas: {f['problemas']}")
        if f["evidencia_clip"]:
            print(f"  evidencia: {f['evidencia_clip']}")
        print(f"  acción:    {f['accion']}")
    print(f"\n{len(filas)} posts publicados con algún problema.")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(filas[0].keys()) if filas else ["id"])
            w.writeheader()
            w.writerows(filas)
        print(f"CSV: {args.csv}", file=sys.stderr)


if __name__ == "__main__":
    main()
