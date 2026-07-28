"""Clips de YouTube: descarga, recorte y atribución.

Publicar un fragmento de un canal ajeno es una decisión editorial tomada a
sabiendas: se hace sin pedir permiso previo y se atienden las reclamaciones si
llegan. Lo que hace este módulo es que esa decisión sea *defendible y
reversible*:

  - **Atribución quemada en el vídeo**, no solo en el caption. El nombre del
    canal va sobreimpreso en la pieza, así que viaja con ella aunque alguien la
    reguarde o la reenvíe.
  - **Procedencia completa en BD** (`VideoClip`): vídeo, canal, tramo exacto,
    quién lo pidió y en qué publicación acabó.
  - **Retirada en un paso**: `retire()` borra el post de Instagram, quita el
    fichero de Cloudinary y registra el motivo.
  - **Tramos cortos** (`MAX_CLIP_S`), nunca un vídeo entero.

DÓNDE CORRE CADA COSA: la descarga NO puede hacerse en el servidor — YouTube
bloquea las IP de datacenter, que es exactamente el motivo por el que las
transcripciones de Juancares se bajan desde la Mac (`infra/local/`). Aquí:

  - `descargar_y_recortar()` corre en la MÁQUINA LOCAL (IP residencial);
  - el resto (alta, consulta, retirada) corre en el servidor.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import VideoClip
from app.services.instagram import config

logger = logging.getLogger(__name__)

# Un clip corto es más defendible y funciona mejor. Instagram admite reels
# largos; aquí se recorta por criterio propio.
MAX_CLIP_S = 60.0
MIN_CLIP_S = 3.0

# Formato de salida: 9:16 para reels.
ANCHO, ALTO = 1080, 1920

_YT_ID = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([\w-]{11})"
)

# Canales de los que NO se cogen clips.
#
# Publicar un fragmento de un canal de fan y publicarlo del canal OFICIAL de la
# banda o de su discográfica no tienen el mismo riesgo: el titular de derechos es
# justo quien reclamaría, e Instagram detecta audio con derechos y puede tumbar
# el post sin que intervenga nadie. Los canales de fan, entrevistas y archivo son
# terreno mucho más tranquilo.
#
# Se comprueba sobre el nombre del canal que devuelve yt-dlp, que es el real, no
# sobre lo que uno crea al pegar la URL.
CANALES_VETADOS = (
    "oficial", "official", "vevo", " - topic", "records", "discos",
    "warner", "sony music", "universal music", "dro east west",
)


def canal_vetado(canal: str) -> str | None:
    """Devuelve el patrón que veta a este canal, o None si se puede usar."""
    c = (canal or "").casefold()
    if not c:
        return None
    return next((p for p in CANALES_VETADOS if p in c), None)


def extraer_video_id(url: str) -> str | None:
    """El id de 11 caracteres de una URL de YouTube, o None si no lo parece."""
    m = _YT_ID.search(url or "")
    return m.group(1) if m else None


def solicitar(
    db: Session, url: str, start_s: float, end_s: float,
    subtitle: str | None = None, requested_by: str | None = None,
) -> VideoClip:
    """Da de alta la petición de un clip. La descarga la hará el daemon local."""
    video_id = extraer_video_id(url)
    if not video_id:
        raise ValueError("no parece una URL de YouTube")
    if end_s - start_s < MIN_CLIP_S:
        raise ValueError(f"el tramo es de menos de {MIN_CLIP_S:.0f} s")
    if end_s - start_s > MAX_CLIP_S:
        raise ValueError(f"el tramo pasa de {MAX_CLIP_S:.0f} s")

    clip = VideoClip(
        video_id=video_id, url=url.strip(), start_s=start_s, end_s=end_s,
        subtitle=(subtitle or "").strip() or None,
        requested_by=requested_by, status="requested",
    )
    db.add(clip)
    db.commit()
    db.refresh(clip)
    logger.info("[clip] solicitado %s (%.0f-%.0f s)", video_id, start_s, end_s)
    return clip


def pendientes(db: Session, max_intentos: int = 3) -> list[VideoClip]:
    """Clips que el daemon local tiene que bajar."""
    return list(db.execute(
        select(VideoClip).where(
            VideoClip.status.in_(("requested", "failed")),
            VideoClip.attempts < max_intentos,
        ).order_by(VideoClip.created_at)
    ).scalars().all())


# --------------------------------------------------------------------------- #
# Descarga y montaje — SOLO en la máquina local (IP residencial)
# --------------------------------------------------------------------------- #
def _ffmpeg(args: list[str]) -> None:
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *args],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {proc.stderr.strip()[:400]}")


def _escapar_drawtext(texto: str) -> str:
    """Escapa el texto para el filtro drawtext de ffmpeg."""
    return (
        texto.replace("\\", "\\\\").replace(":", "\\:")
        .replace("'", "’").replace("%", "\\%")
    )


def descargar_y_recortar(
    url: str, start_s: float, end_s: float, canal: str,
    subtitulo: str | None, destino: str,
) -> dict:
    """Baja el vídeo, recorta el tramo, lo pasa a 9:16 y quema la atribución.

    CORRE EN LA MÁQUINA LOCAL: yt-dlp desde una IP de datacenter recibe un
    bloqueo de YouTube (mismo motivo que el daemon de transcripciones).

    Devuelve metadatos del clip resultante.
    """
    import yt_dlp

    duracion = end_s - start_s
    with tempfile.TemporaryDirectory() as tmp:
        crudo = os.path.join(tmp, "crudo.mp4")
        opciones = {
            "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "outtmpl": crudo,
            "quiet": True,
            "noprogress": True,
            "merge_output_format": "mp4",
            # Solo el tramo pedido: no se descarga el vídeo entero.
            "download_ranges": yt_dlp.utils.download_range_func(
                None, [(start_s, end_s)]
            ),
            "force_keyframes_at_cuts": True,
        }
        with yt_dlp.YoutubeDL(opciones) as ydl:
            info = ydl.extract_info(url, download=True)

        # El canal real solo se conoce ahora: se comprueba aquí, no al pedirlo.
        canal_real = (info or {}).get("uploader") or canal
        vetado = canal_vetado(canal_real)
        if vetado:
            raise RuntimeError(
                f"canal vetado: «{canal_real}» (coincide con «{vetado}»). "
                "No se cogen clips de canales oficiales ni de discográficas: "
                "el titular de derechos es quien reclamaría y Meta puede tumbar "
                "el post automáticamente. Busca el mismo material en un canal "
                "de fan, de archivo o de entrevistas."
            )

        if not os.path.exists(crudo):
            raise RuntimeError("yt-dlp no dejó fichero")

        # A 9:16 con relleno desenfocado + atribución quemada abajo.
        #
        # OJO con el escalado, que ya falló una vez: un vídeo 16:9 escalado a
        # ANCHO=1080 queda en 1080x608, y recortar 1920 de alto de eso revienta
        # con "Invalid too big or non positive size". Hay que escalar para
        # CUBRIR el lienzo (`increase`) antes de recortar, y para que QUEPA
        # (`decrease`) en el primer plano. Así vale cualquier proporción de
        # origen, horizontal o vertical.
        credito = _escapar_drawtext(f"Vídeo: {canal}" if canal else "Vídeo de YouTube")
        filtros = [
            f"[0:v]scale={ANCHO}:{ALTO}:force_original_aspect_ratio=increase,"
            f"crop={ANCHO}:{ALTO},boxblur=28:2[bg]",
            f"[0:v]scale={ANCHO}:{ALTO}:force_original_aspect_ratio=decrease[fg]",
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[v0]",
        ]
        texto = (
            f"[v0]drawtext=text='{credito}':fontcolor=white@0.92:fontsize=34:"
            f"x=(w-text_w)/2:y=h-190:box=1:boxcolor=black@0.55:boxborderw=16"
        )
        if subtitulo:
            texto += (
                f"[v1];[v1]drawtext=text='{_escapar_drawtext(subtitulo)}':"
                f"fontcolor=white:fontsize=52:x=(w-text_w)/2:y=h-420:"
                f"box=1:boxcolor=black@0.5:boxborderw=18"
            )
        filtros.append(texto + "[v]")

        _ffmpeg([
            "-i", crudo,
            "-filter_complex", ";".join(filtros),
            "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
            "-t", f"{duracion}",
            destino,
        ])

    return {
        "path": destino,
        "duration_s": duracion,
        "video_title": (info or {}).get("title"),
        "channel_title": (info or {}).get("uploader") or canal,
        "channel_url": (info or {}).get("uploader_url"),
        "size_mb": os.path.getsize(destino) / 1024 / 1024,
    }


# --------------------------------------------------------------------------- #
# Retirada — la válvula que hace asumible publicar sin permiso previo
# --------------------------------------------------------------------------- #
def retire(db: Session, clip: VideoClip, motivo: str) -> tuple[bool, str]:
    """Retira un clip: borra el post de Instagram y el fichero de Cloudinary.

    Pensado para responder a una reclamación en minutos. Es best-effort en cada
    paso: si el borrado en Instagram falla, se sigue y se deja constancia, para
    que el clip quede marcado como retirado igualmente.
    """
    from app.services.instagram import cloudinary_upload, graph_api

    problemas: list[str] = []

    if clip.ig_media_id:
        try:
            import httpx
            with httpx.Client(timeout=20.0) as client:
                r = client.delete(
                    f"{graph_api.GRAPH}/{clip.ig_media_id}",
                    params={"access_token": config.INSTAGRAM_ACCESS_TOKEN},
                )
            if r.status_code >= 400:
                problemas.append(f"Instagram: {r.text[:120]}")
        except Exception as exc:  # noqa: BLE001
            problemas.append(f"Instagram: {exc}")

    if clip.cloudinary_public_id:
        try:
            if not cloudinary_upload.destroy(
                clip.cloudinary_public_id, resource_type="video"
            ):
                problemas.append("Cloudinary no confirmó el borrado")
        except Exception as exc:  # noqa: BLE001
            problemas.append(f"Cloudinary: {exc}")

    clip.status = "retired"
    clip.retired_at = datetime.now(timezone.utc)
    clip.retired_reason = motivo
    if problemas:
        clip.error = " · ".join(problemas)
    db.commit()

    if problemas:
        return False, "Retirado en nuestro registro, pero: " + " · ".join(problemas)
    # NO se promete que ya sea inaccesible: el borrado en Cloudinary es
    # inmediato, pero la copia del CDN tarda unos minutos en invalidarse.
    return True, (
        "Clip retirado. El fichero puede seguir sirviéndose desde la caché del "
        "CDN unos minutos más"
    )
