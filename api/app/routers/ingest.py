"""Endpoints de ingesta de YouTube para el DAEMON LOCAL de la Mac.

Pipeline "1 click → autónomo" (ver project_robelyrics_youtube_juancares):
  - El server DETECTA uploads (scripts.youtube.detect_uploads) y el admin aprueba
    el batch con un click (endpoint /youtube-ingest en public.py).
  - El daemon launchd de la Mac (IP residencial, esquiva el antibot de YouTube)
    hace polling de `pending`, transcribe en local y EMPUJA la transcripción aquí.

Estos endpoints NO son login de usuario: se autentican con un bearer compartido
(INGEST_API_KEY), porque el cliente es una máquina, no una persona. El texto
recibido se persiste como InterpretationSource (kind según `target`); el embed
real lo hace el Pipeline 1 semanal (embed_interpretations / embed_robe_voice).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import YouTubeIngestQueue
from app.db.session import get_db

router = APIRouter(prefix="/ingest/youtube", tags=["ingest"])

# Reintentos automáticos de un vídeo que falló (yt-dlp/Whisper transitorio).
MAX_ATTEMPTS = 3

# quality_score por defecto según el kind (alineado con import_interview_transcripts).
_DEFAULT_QUALITY = {
    "youtube_transcript": 0.7,
    "robe_interview": 0.8,
    "about_robe": 0.5,
}


def require_ingest_key(
    authorization: str | None = Header(default=None),
) -> None:
    """Valida el bearer INGEST_API_KEY. 401 si falta o no coincide. 503 si el
    server no tiene la key configurada (mejor fallar claro que dejar abierto)."""
    key = get_settings().ingest_api_key
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ingest no configurado",
        )
    expected = f"Bearer {key}"
    if not authorization or authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="bad ingest key"
        )


class PendingItem(BaseModel):
    id: int
    video_id: str
    url: str
    title: str | None = None
    target: str


class CompleteIn(BaseModel):
    # Suelo ABSOLUTO, solo contra payloads vacíos o basura. El criterio fino lo
    # aplica el daemon con `min_chars_for`, que es quien conoce la duración del
    # audio: aquí había un 100 fijo que rechazaba con un 422 opaco cualquier pieza
    # legítimamente corta (un tráiler de 40 s, o los shorts de @tesonica), y el
    # daemon lo registraba como fallo genérico sin decir que venía del servidor.
    content_clean: str = Field(min_length=25)
    title: str | None = None
    published_at: datetime | None = None
    quality_score: float | None = None


class FailIn(BaseModel):
    error: str = Field(max_length=2000)


class OkOut(BaseModel):
    ok: bool = True
    status: str


@router.get(
    "/pending",
    response_model=list[PendingItem],
    dependencies=[Depends(require_ingest_key)],
)
def list_pending(db: Session = Depends(get_db)) -> list[YouTubeIngestQueue]:
    """Vídeos listos para que el daemon los transcriba: los `approved` y los
    `failed` con margen de reintento (< MAX_ATTEMPTS), por si el fallo fue
    transitorio (yt-dlp/Whisper)."""
    return (
        db.query(YouTubeIngestQueue)
        .filter(
            or_(
                YouTubeIngestQueue.status == "approved",
                and_(
                    YouTubeIngestQueue.status == "failed",
                    YouTubeIngestQueue.attempts < MAX_ATTEMPTS,
                ),
            )
        )
        .order_by(YouTubeIngestQueue.approved_at.asc())
        .all()
    )


def _get_or_404(db: Session, item_id: int) -> YouTubeIngestQueue:
    row = db.get(YouTubeIngestQueue, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="item no encontrado")
    return row


@router.post(
    "/{item_id}/claim",
    response_model=OkOut,
    dependencies=[Depends(require_ingest_key)],
)
def claim(item_id: int, db: Session = Depends(get_db)) -> OkOut:
    """Marca `processing` para que dos daemons no pisen el mismo vídeo."""
    row = _get_or_404(db, item_id)
    if row.status not in ("approved", "processing", "failed"):
        raise HTTPException(
            status_code=409, detail=f"estado no reclamable: {row.status}"
        )
    row.status = "processing"
    db.commit()
    return OkOut(status=row.status)


@router.post(
    "/{item_id}/complete",
    response_model=OkOut,
    dependencies=[Depends(require_ingest_key)],
)
def complete(
    item_id: int, payload: CompleteIn, db: Session = Depends(get_db)
) -> OkOut:
    """Recibe la transcripción del daemon, la persiste como InterpretationSource
    (kind según target) y marca el item `done`. Idempotente por (kind, url)."""
    row = _get_or_404(db, item_id)

    # Import perezoso: el helper de upsert vive en los scripts de research.
    from scripts.research.common import clean_text, upsert_source

    content = (payload.content_clean or "").strip()
    default_q = _DEFAULT_QUALITY.get(row.kind, 0.7)
    upsert_source(
        db,
        kind=row.kind,
        url=row.url,
        title=payload.title or row.title,
        author=row.author,
        published_at=payload.published_at or row.published_at,
        content_raw=content,
        content_clean=clean_text(content),
        quality_score=payload.quality_score or default_q,
        for_seo_only=False,
    )
    row.status = "done"
    row.error = None
    row.done_at = datetime.now(timezone.utc)
    db.commit()
    return OkOut(status=row.status)


@router.post(
    "/{item_id}/fail",
    response_model=OkOut,
    dependencies=[Depends(require_ingest_key)],
)
def fail(item_id: int, payload: FailIn, db: Session = Depends(get_db)) -> OkOut:
    """El daemon reporta un fallo (yt-dlp/Whisper). Suma intento y marca failed;
    el daemon reintenta `failed`/`approved` en la siguiente pasada.

    Un item YA COMPLETADO no se degrada. Con dos pasadas solapadas —el launchd cada
    15 min y una lanzada a mano— la segunda recibe un 409 al reclamar lo que la
    primera ya terminó, y reportaba ese 409 como fallo: el item quedaba `failed` con
    su `done_at` sellado, y el daemon lo volvía a descargar y transcribir, pagando
    Whisper por algo que ya estaba en el corpus.
    """
    row = _get_or_404(db, item_id)
    row.error = payload.error[:2000]
    row.attempts = (row.attempts or 0) + 1
    if row.status != "done":
        row.status = "failed"
    db.commit()
    return OkOut(status=row.status)


# =========================================================================== #
# Clips de vídeo para Instagram
# =========================================================================== #
# Mismo reparto de trabajo que las transcripciones y por el mismo motivo: la IP
# del servidor está bloqueada por YouTube, así que descarga el daemon de la Mac
# y sube el resultado ya recortado y con la atribución quemada.

clips_router = APIRouter(prefix="/ingest/clips", tags=["ingest"])


class ClipPending(BaseModel):
    id: int
    url: str
    video_id: str
    start_s: float
    end_s: float
    subtitle: str | None = None
    channel_title: str | None = None
    attempts: int


class ClipComplete(BaseModel):
    """Lo que manda el daemon cuando ya ha subido el clip a Cloudinary."""
    url_cdn: str
    cloudinary_public_id: str | None = None
    duration_s: float | None = None
    video_title: str | None = None
    channel_title: str | None = None
    channel_url: str | None = None


@clips_router.get("/pending", response_model=list[ClipPending])
def clips_pending(
    db: Session = Depends(get_db),
    _: None = Depends(require_ingest_key),
) -> list[ClipPending]:
    """Clips que quedan por descargar."""
    from app.services.instagram import video_clips as _vc

    return [
        ClipPending(
            id=c.id, url=c.url, video_id=c.video_id, start_s=c.start_s,
            end_s=c.end_s, subtitle=c.subtitle, channel_title=c.channel_title,
            attempts=c.attempts,
        )
        for c in _vc.pendientes(db, max_intentos=MAX_ATTEMPTS)
    ]


@clips_router.post("/{clip_id}/claim")
def clips_claim(
    clip_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_ingest_key),
) -> dict:
    """Marca el clip como en descarga, para que dos daemons no lo dupliquen."""
    from app.db.models import VideoClip

    clip = db.get(VideoClip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="clip no encontrado")
    clip.status = "downloading"
    clip.attempts += 1
    db.commit()
    return {"ok": True, "attempts": clip.attempts}


@clips_router.post("/{clip_id}/complete")
def clips_complete(
    clip_id: int,
    payload: ClipComplete,
    db: Session = Depends(get_db),
    _: None = Depends(require_ingest_key),
) -> dict:
    """El clip ya está en Cloudinary: se guarda su URL y su procedencia."""
    from app.db.models import VideoClip

    clip = db.get(VideoClip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="clip no encontrado")
    clip.url_cdn = payload.url_cdn
    clip.cloudinary_public_id = payload.cloudinary_public_id
    clip.duration_s = payload.duration_s
    # La procedencia real la sabe quien descargó, no quien pidió el clip.
    clip.video_title = payload.video_title or clip.video_title
    clip.channel_title = payload.channel_title or clip.channel_title
    clip.channel_url = payload.channel_url or clip.channel_url
    clip.status = "ready"
    clip.error = None

    # La publicación del clip se creó al pedirlo, con el tema que escribió el
    # admin. Ahora se le añade la procedencia REAL, que hasta la descarga no se
    # conocía: es lo que acredita de dónde sale el vídeo y va en el caption.
    if clip.queue_item_id:
        from app.db.models import InstagramQueueItem

        item = db.get(InstagramQueueItem, clip.queue_item_id)
        if item is not None and item.status != "published":
            item.source_name = clip.channel_title or item.source_name
            item.source_url = clip.channel_url or clip.url or item.source_url
            if not (item.summary or "").strip() and clip.video_title:
                item.summary = clip.video_title[:500]

    db.commit()
    return {"ok": True, "status": clip.status}


@clips_router.post("/{clip_id}/fail")
def clips_fail(
    clip_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _: None = Depends(require_ingest_key),
) -> dict:
    from app.db.models import VideoClip

    clip = db.get(VideoClip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="clip no encontrado")
    clip.status = "failed"
    clip.error = str(payload.get("error", ""))[:2000]
    db.commit()
    return {"ok": True, "attempts": clip.attempts}
