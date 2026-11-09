"""Añadir una URL al corpus a mano, desde el panel.

Hasta el 09-11-2026 solo se podía desde la terminal (`enqueue_audio`) y un vídeo
de Juancares estrenado ocho horas después de la pasada de `detect_uploads`
esperaba tres días a que lo viera, y luego un clic, y luego su hueco en el tope
semanal. Añadirlo a mano ya es la decisión: entra `approved`, va el primero y no
gasta hueco de la semana (`corpus_ritmo`). El presupuesto de Whisper sí lo
respeta: con subtítulos es gratis, sin ellos espera al mes siguiente si no cabe.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import InterpretationSource, YouTubeIngestQueue

logger = logging.getLogger(__name__)

# Lo que se elige en el formulario → cómo entra (mismo criterio que corpus_trust:
# A voz, B medio, C fan). Solo Robe va a la voz del consultorio.
TIPOS = {
    "robe_interview": ("robe_voice", "A"),
    "entorno_interview": ("corpus", "A"),
    "media_report": ("corpus", "B"),
    "youtube_transcript": ("corpus", "C"),
}


class ManualError(ValueError):
    """El mensaje se enseña tal cual en el panel."""


def clave(url: str) -> str:
    """`video_id` sintético de un audio que no es de YouTube: la cola lo exige."""
    return "audio:" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:24]


def _detalles_youtube(video_id: str) -> dict:
    """Título, canal y duración por `videos.list`: 1 unidad de cuota, no 100."""
    import httpx

    from app.config import get_settings
    from scripts.youtube.corpus_search import detalles

    key = get_settings().youtube_api_key
    if not key:
        return {}
    with httpx.Client(timeout=20) as client:
        return detalles(client, key, [video_id]).get(video_id) or {}


def _ya_en_el_corpus(db: Session, video_id: str, url: str) -> bool:
    patron = video_id if not video_id.startswith("audio:") else url
    return db.query(InterpretationSource.id).filter(
        InterpretationSource.url.contains(patron)).first() is not None


def anadir(db: Session, url: str, tipo: str, *, titulo: str | None = None,
           autor: str | None = None, detalles=None) -> dict:
    """Devuelve {"estado": "nuevo"|"priorizado"|"ya_estaba", "id", "mensaje"}."""
    from app.services.instagram.video_clips import extraer_video_id

    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise ManualError("Eso no parece una URL.")
    if tipo not in TIPOS:
        raise ManualError("Elige cómo entra.")
    target, nivel = TIPOS[tipo]
    vid = extraer_video_id(url)
    if vid:
        url = f"https://www.youtube.com/watch?v={vid}"
    else:
        vid = clave(url)
    ahora = datetime.now(UTC)
    nota = f"añadido a mano el {ahora.date().isoformat()}"

    if _ya_en_el_corpus(db, vid, url):
        fila = db.query(YouTubeIngestQueue).filter_by(video_id=vid).first()
        return {"estado": "ya_estaba", "id": fila.id if fila else None,
                "mensaje": "Ya está en el corpus."}
    ya = db.query(YouTubeIngestQueue).filter_by(video_id=vid).first()
    if ya is not None:
        if ya.status in ("done", "processing"):
            estado = "ya en el corpus" if ya.status == "done" else "transcribiéndose ahora"
            return {"estado": "ya_estaba", "id": ya.id,
                    "mensaje": f"Ya estaba en la cola (#{ya.id}): {estado}."}
        antes = ya.status
        ya.status = "approved"
        ya.approved_at = ahora
        ya.attempts = 0
        ya.error = None
        ya.motivos = [*(ya.motivos or []),
                      f"{nota} (estaba «{antes}», encontrado por {ya.descubierto_por or '—'})"]
        ya.descubierto_por = "manual"
        db.commit()
        return {"estado": "priorizado", "id": ya.id,
                "mensaje": f"Ya estaba en la cola (#{ya.id}, «{antes}»): aprobado y el primero."}

    info = {}
    if not vid.startswith("audio:"):
        from scripts.youtube.corpus_search import CuotaAgotada

        sin_cuota = False
        try:
            info = (detalles or _detalles_youtube)(vid)
        except CuotaAgotada:
            sin_cuota = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("[corpus-manual] videos.list falló para %s: %s", vid, exc)
        if not info and not titulo:
            # Un 403 de cuota no dice nada del vídeo: decir «¿privado o borrado?»
            # sería mentir. La cuota se reinicia a las 09:00 de Madrid.
            raise ManualError(
                "Se ha agotado la cuota diaria de YouTube (vuelve a las 9:00). Escribe tú "
                "el título o prueba entonces." if sin_cuota else
                "YouTube no devuelve ese vídeo (¿privado o borrado?). Si existe, escribe tú "
                "el título.")
    elif not titulo:
        raise ManualError("Un audio que no es de YouTube necesita título.")
    publicado = info.get("published_at")
    fila = YouTubeIngestQueue(
        video_id=vid, url=url, title=(titulo or info.get("title") or vid)[:500],
        channel=(autor or info.get("channel_title") or None or "")[:120] or None,
        author=(autor or info.get("channel_title") or "")[:120] or None,
        channel_id=info.get("channel_id"),
        target=target, kind=tipo, status="approved", approved_at=ahora, nivel=nivel,
        motivos=[nota], descubierto_por="manual", duration_s=info.get("duration_s"),
        published_at=(datetime.fromisoformat(publicado.replace("Z", "+00:00"))
                      if publicado else None),
    )
    db.add(fila)
    db.commit()
    return {"estado": "nuevo", "id": fila.id,
            "mensaje": f"Añadido (#{fila.id}): tu Mac lo transcribe en su próxima pasada."}
