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
from sqlalchemy.orm import Session

from sqlalchemy import and_, or_

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
    content_clean: str = Field(min_length=100)
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
    el daemon reintenta `failed`/`approved` en la siguiente pasada."""
    row = _get_or_404(db, item_id)
    row.status = "failed"
    row.error = payload.error[:2000]
    row.attempts = (row.attempts or 0) + 1
    db.commit()
    return OkOut(status=row.status)
