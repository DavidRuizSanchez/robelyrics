"""Endpoints admin: alta de fuentes fan + trigger de pipeline.

Tres modos de alta:
  - "text"    → contenido pegado tal cual.
  - "url"     → scrape de la URL con BeautifulSoup.
  - "youtube" → descarga transcript con youtube-transcript-api.

Tras alta, find_referenced_titles() detecta canciones mencionadas y devuelve
los slugs. Un endpoint /process dispara el pipeline (embed + distill + payload
+ vectorize) para esas canciones.

Pipeline síncrono: el endpoint puede tardar 30-90s por canción afectada.
"""
from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import Album, Artist, InterpretationSource, SeoContent, Song, User
from app.db.session import get_db
from app.services.auth import get_current_admin
from scripts.research.common import (
    clean_text,
    find_referenced_titles,
    get_all_song_titles,
    upsert_source,
)
from scripts.research.fetch_blogs import HEADERS, extract_article_text

router = APIRouter(prefix="/admin", tags=["admin"])


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class SourceCreateIn(BaseModel):
    mode: Literal["text", "url", "youtube"]
    kind: str  # blog, forum, youtube_transcript, youtube_comment, manual, ...
    url: str
    title: str | None = None
    author: str | None = None
    content: str | None = None  # mode=text
    fetch_url: str | None = None  # mode=url (si difiere de url)
    youtube_url: str | None = None  # mode=youtube


class SourceCreateOut(BaseModel):
    source_id: int
    referenced_song_ids: list[int]
    referenced_song_slugs: list[str]


class SourceListItem(BaseModel):
    id: int
    kind: str
    url: str
    title: str | None
    author: str | None
    fetched_at: datetime
    referenced_song_ids: list[int] | None
    n_referenced: int


class SourceProcessOut(BaseModel):
    source_id: int
    processed_song_slugs: list[str]
    log: list[str]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _extract_video_id(yt_url: str) -> str | None:
    """Extrae videoId de cualquier URL de YouTube."""
    p = urlparse(yt_url)
    if p.netloc in ("youtu.be",):
        return p.path.lstrip("/").split("/")[0] or None
    if "youtube.com" in p.netloc:
        if p.path.startswith("/watch"):
            qs = parse_qs(p.query)
            v = qs.get("v")
            return v[0] if v else None
        if p.path.startswith("/embed/") or p.path.startswith("/shorts/"):
            return p.path.split("/")[2]
    # ID a pelo
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", yt_url):
        return yt_url
    return None


def _scrape_url(url: str) -> str:
    """Descarga la URL y devuelve texto del artículo. Lanza HTTPException si falla."""
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            r = client.get(url, headers=HEADERS)
        if r.status_code != 200:
            raise HTTPException(
                status_code=400,
                detail=f"fetch_url devolvió {r.status_code}",
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"error fetch_url: {e}") from e

    text = extract_article_text(r.text)
    if not text or len(text) < 200:
        raise HTTPException(
            status_code=400,
            detail="contenido extraído demasiado corto (<200 chars)",
        )
    return text


def _fetch_youtube_transcript(yt_url: str) -> tuple[str, str]:
    """Descarga transcript del vídeo. Devuelve (text, video_id).

    Lazy-import de youtube_transcript_api (es una dep pesada).
    """
    video_id = _extract_video_id(yt_url)
    if not video_id:
        raise HTTPException(status_code=400, detail="URL de YouTube no reconocida")

    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        CouldNotRetrieveTranscript,
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
    )

    try:
        api = YouTubeTranscriptApi()
        fetched = api.fetch(video_id, languages=["es", "es-ES", "en"])
    except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable, CouldNotRetrieveTranscript) as e:
        raise HTTPException(
            status_code=400,
            detail=f"transcript no disponible para {video_id}: {type(e).__name__}",
        ) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"error transcript: {e}") from e

    text = " ".join(s.text for s in fetched.snippets if s.text)
    text = clean_text(text) or ""
    if len(text) < 200:
        raise HTTPException(status_code=400, detail="transcript demasiado corto")
    return text, video_id


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.post("/sources", response_model=SourceCreateOut)
def create_source(
    body: SourceCreateIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> SourceCreateOut:
    if body.mode == "text":
        if not body.content or len(body.content.strip()) < 50:
            raise HTTPException(status_code=400, detail="contenido requerido (≥50 chars)")
        raw = body.content
    elif body.mode == "url":
        target = body.fetch_url or body.url
        raw = _scrape_url(target)
    elif body.mode == "youtube":
        target = body.youtube_url or body.url
        raw, vid = _fetch_youtube_transcript(target)
        # Normaliza la URL canónica al watch?v= si era acortada
        if not body.url or "youtu" not in body.url:
            body.url = f"https://www.youtube.com/watch?v={vid}"
    else:
        raise HTTPException(status_code=400, detail=f"mode desconocido: {body.mode}")

    cleaned = clean_text(raw)

    # Detectar canciones mencionadas
    all_titles = get_all_song_titles(db)
    referenced_ids = find_referenced_titles(cleaned or "", all_titles)

    source_id = upsert_source(
        db,
        kind=body.kind,
        url=body.url,
        title=body.title,
        author=body.author,
        content_raw=raw,
        content_clean=cleaned,
        referenced_song_ids=referenced_ids if referenced_ids else None,
        quality_score=0.7,  # admin-curated → confianza alta
    )
    db.commit()

    referenced_slugs = []
    if referenced_ids:
        rows = (
            db.query(Song.slug)
            .filter(Song.id.in_(referenced_ids))
            .all()
        )
        referenced_slugs = [r[0] for r in rows]

    return SourceCreateOut(
        source_id=source_id,
        referenced_song_ids=referenced_ids,
        referenced_song_slugs=referenced_slugs,
    )


@router.post("/sources/{source_id}/process", response_model=SourceProcessOut)
def process_source(
    source_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> SourceProcessOut:
    src = db.query(InterpretationSource).filter(InterpretationSource.id == source_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="source not found")

    referenced_ids = src.referenced_song_ids or []
    if not referenced_ids:
        raise HTTPException(
            status_code=400,
            detail="esta fuente no menciona ninguna canción del catálogo",
        )

    slugs = [
        r[0] for r in db.query(Song.slug).filter(Song.id.in_(referenced_ids)).all()
    ]

    log_lines: list[str] = []

    def run(cmd: list[str]) -> None:
        log_lines.append(f"$ {' '.join(cmd)}")
        try:
            r = subprocess.run(
                cmd,
                cwd="/app",
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            tail_out = (r.stdout or "").splitlines()[-3:]
            tail_err = (r.stderr or "").splitlines()[-3:]
            log_lines.extend(tail_out)
            log_lines.extend(tail_err)
            if r.returncode != 0:
                raise HTTPException(
                    status_code=500,
                    detail=f"comando falló ({r.returncode}): {cmd}",
                )
        except subprocess.TimeoutExpired as e:
            raise HTTPException(status_code=500, detail=f"timeout en {cmd}") from e

    # 1) Re-link de fuentes (por si alguna ya existía y no estaba vinculada)
    run(["python", "-m", "scripts.research.link_sources_to_songs"])
    # 2) Embedding de los chunks nuevos en Qdrant (interpretations_v1)
    run(["python", "-m", "scripts.research.embed_interpretations"])
    # 3) Re-distill por canción afectada
    for slug in slugs:
        run(["python", "-m", "scripts.research.distill", "--song-slug", slug])
    # 4) Update payload (rellena campos derivados)
    run(["python", "-m", "scripts.research.update_interpretations_payload"])
    # 5) Re-vectorize consensus
    run(["python", "-m", "scripts.research.vectorize_consensus"])

    return SourceProcessOut(
        source_id=source_id,
        processed_song_slugs=slugs,
        log=log_lines,
    )


@router.get("/sources", response_model=list[SourceListItem])
def list_sources(
    limit: int = 50,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[SourceListItem]:
    rows = (
        db.query(InterpretationSource)
        .order_by(InterpretationSource.fetched_at.desc())
        .limit(min(max(limit, 1), 200))
        .all()
    )
    return [
        SourceListItem(
            id=r.id,
            kind=r.kind,
            url=r.url,
            title=r.title,
            author=r.author,
            fetched_at=r.fetched_at,
            referenced_song_ids=r.referenced_song_ids,
            n_referenced=len(r.referenced_song_ids or []),
        )
        for r in rows
    ]


# --------------------------------------------------------------------------- #
# SEO content (revisión humana del contenido generado por LLM)
# --------------------------------------------------------------------------- #
class SeoContentListItem(BaseModel):
    id: int
    entity_type: str  # artist|album|song
    slug: str
    entity_label: str  # ej. "Extremoduro · Agila · Asco"
    chars: int
    generated_at: datetime
    generated_by: str
    reviewed_at: datetime | None
    published: bool


class SeoContentOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    slug: str
    entity_label: str
    body_md: str
    meta_title: str | None
    meta_description: str | None
    schema_jsonld: dict | None
    generated_at: datetime
    generated_by: str
    reviewed_at: datetime | None
    published: bool
    public_url: str  # ruta canónica relativa


class SeoContentUpdateIn(BaseModel):
    body_md: str
    meta_title: str | None = None
    meta_description: str | None = None


def _entity_label_and_url(db: Session, entity_type: str, entity_id: int) -> tuple[str, str]:
    """Devuelve (label legible, ruta pública canónica) para una entidad."""
    if entity_type == "artist":
        a = db.query(Artist).filter(Artist.id == entity_id).first()
        if not a:
            return ("?", "")
        return (a.name, f"/{a.slug}")
    if entity_type == "album":
        al = db.query(Album).filter(Album.id == entity_id).first()
        if not al:
            return ("?", "")
        return (f"{al.artist.name} · {al.title}", f"/{al.artist.slug}/{al.slug}")
    if entity_type == "song":
        s = db.query(Song).filter(Song.id == entity_id).first()
        if not s:
            return ("?", "")
        al = s.album
        return (
            f"{al.artist.name} · {al.title} · {s.title}",
            f"/{al.artist.slug}/{al.slug}/{s.slug}",
        )
    return ("?", "")


@router.get("/seo", response_model=list[SeoContentListItem])
def list_seo(
    status: Literal["all", "unreviewed", "reviewed", "published"] = "all",
    entity_type: Literal["all", "artist", "album", "song"] = "all",
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[SeoContentListItem]:
    q = db.query(SeoContent)
    if status == "unreviewed":
        q = q.filter(SeoContent.reviewed_at.is_(None))
    elif status == "reviewed":
        q = q.filter(SeoContent.reviewed_at.is_not(None), SeoContent.published.is_(False))
    elif status == "published":
        q = q.filter(SeoContent.published.is_(True))
    if entity_type != "all":
        q = q.filter(SeoContent.entity_type == entity_type)
    rows = q.order_by(SeoContent.entity_type, SeoContent.slug).all()
    out = []
    for r in rows:
        label, _ = _entity_label_and_url(db, r.entity_type, r.entity_id)
        out.append(
            SeoContentListItem(
                id=r.id,
                entity_type=r.entity_type,
                slug=r.slug,
                entity_label=label,
                chars=len(r.body_md or ""),
                generated_at=r.generated_at,
                generated_by=r.generated_by,
                reviewed_at=r.reviewed_at,
                published=r.published,
            )
        )
    return out


@router.get("/seo/{seo_id}", response_model=SeoContentOut)
def get_seo(
    seo_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> SeoContentOut:
    row = db.query(SeoContent).filter(SeoContent.id == seo_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="seo_content no encontrado")
    label, public_url = _entity_label_and_url(db, row.entity_type, row.entity_id)
    return SeoContentOut(
        id=row.id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        slug=row.slug,
        entity_label=label,
        body_md=row.body_md,
        meta_title=row.meta_title,
        meta_description=row.meta_description,
        schema_jsonld=row.schema_jsonld,
        generated_at=row.generated_at,
        generated_by=row.generated_by,
        reviewed_at=row.reviewed_at,
        published=row.published,
        public_url=public_url,
    )


@router.put("/seo/{seo_id}", response_model=SeoContentOut)
def update_seo(
    seo_id: int,
    body: SeoContentUpdateIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> SeoContentOut:
    """Guarda cambios y marca como revisado (mantiene published actual)."""
    row = db.query(SeoContent).filter(SeoContent.id == seo_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="seo_content no encontrado")
    row.body_md = body.body_md
    row.meta_title = body.meta_title
    row.meta_description = body.meta_description
    row.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return get_seo(seo_id, db=db)  # type: ignore[arg-type]


@router.post("/seo/{seo_id}/publish", response_model=SeoContentOut)
def publish_seo(
    seo_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> SeoContentOut:
    row = db.query(SeoContent).filter(SeoContent.id == seo_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="seo_content no encontrado")
    if row.reviewed_at is None:
        row.reviewed_at = datetime.now(timezone.utc)
    row.published = True
    db.commit()
    return get_seo(seo_id, db=db)  # type: ignore[arg-type]


@router.post("/seo/{seo_id}/unpublish", response_model=SeoContentOut)
def unpublish_seo(
    seo_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> SeoContentOut:
    row = db.query(SeoContent).filter(SeoContent.id == seo_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="seo_content no encontrado")
    row.published = False
    db.commit()
    return get_seo(seo_id, db=db)  # type: ignore[arg-type]
