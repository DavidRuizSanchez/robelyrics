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

import ipaddress
import os
import re
import socket
import subprocess
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import (
    Album,
    Artist,
    InterpretationSource,
    SeoContent,
    SeoTemplate,
    Song,
    User,
)
from app.db.session import get_db
from app.services.auth import get_current_admin
from app.services.rate_limit import limiter
from app.services.seo_templates import render_with_context, resolve_all
from scripts.research.common import (
    clean_text,
    find_referenced_titles,
    get_all_song_titles,
    upsert_source,
)
from scripts.research.fetch_blogs import HEADERS, extract_article_text

router = APIRouter(prefix="/admin", tags=["admin"])


# --------------------------------------------------------------------------- #
# SSRF guard
# --------------------------------------------------------------------------- #
def _validate_external_url(value: str) -> str:
    """Acepta sólo http/https con host que NO resuelva a redes privadas
    (RFC1918, loopback, link-local, ULA IPv6, multicast). Mitiga SSRF a los
    servicios internos del compose (qdrant, postgres, api) cuando un admin
    legítimo pega una URL maliciosa o un atacante se hace con la sesión.

    Hay una race entre este validate y el fetch real (DNS rebinding) — es
    suficiente para beta. Hardening real: resolver una sola vez aquí y
    pasar la IP literal al cliente HTTP.
    """
    if not value:
        raise ValueError("url vacía")
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"scheme no permitido: {parsed.scheme!r} (sólo http/https)")
    host = parsed.hostname
    if not host:
        raise ValueError("url sin host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"host no resoluble: {host}") from e
    for family, _, _, _, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(
                f"host {host} resuelve a una IP privada/loopback ({ip_str}); SSRF bloqueado"
            )
    return value


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

    @field_validator("url", "fetch_url", "youtube_url")
    @classmethod
    def _block_ssrf(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        return _validate_external_url(v)


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
@limiter.limit("10/hour")
def create_source(
    request: Request,
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
                # Bajado de 600s a 120s. Los pipelines de research están
                # diseñados para ser idempotentes; si algo tarda más de 2
                # min suele ser sospechoso. Re-ejecutable manualmente.
                timeout=120,
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
    h1: str | None
    schema_jsonld: dict | None
    generated_at: datetime
    generated_by: str
    reviewed_at: datetime | None
    published: bool
    public_url: str  # ruta canónica relativa
    # Valores resueltos aplicando plantilla cuando el override es NULL.
    # El frontend los usa como placeholder en el editor.
    resolved_title: str
    resolved_description: str
    resolved_h1: str


class SeoContentUpdateIn(BaseModel):
    body_md: str
    meta_title: str | None = None
    meta_description: str | None = None
    h1: str | None = None


class BulkIdsIn(BaseModel):
    ids: list[int]


class BulkResultOut(BaseModel):
    updated: int
    skipped: list[int]


class SeoTemplateIn(BaseModel):
    entity_type: Literal["artist", "album", "song"]
    kind: str | None = None
    field: Literal["title", "description", "h1"]
    template: str
    notes: str | None = None


class SeoTemplateOut(BaseModel):
    id: int
    entity_type: str
    kind: str | None
    field: str
    template: str
    notes: str | None
    updated_at: datetime


class TemplatePreviewIn(BaseModel):
    entity_type: Literal["artist", "album", "song"]
    kind: str | None = None
    field: Literal["title", "description", "h1"]
    template: str
    sample_entity_id: int | None = None  # si NULL, usa la primera entidad disponible


class TemplatePreviewOut(BaseModel):
    rendered: str
    context: dict[str, str]
    sample_entity_label: str


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
    resolved = resolve_all(db, row)
    return SeoContentOut(
        id=row.id,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        slug=row.slug,
        entity_label=label,
        body_md=row.body_md,
        meta_title=row.meta_title,
        meta_description=row.meta_description,
        h1=row.h1,
        schema_jsonld=row.schema_jsonld,
        generated_at=row.generated_at,
        generated_by=row.generated_by,
        reviewed_at=row.reviewed_at,
        published=row.published,
        public_url=public_url,
        resolved_title=resolved["title"],
        resolved_description=resolved["description"],
        resolved_h1=resolved["h1"],
    )


def _normalize_optional(value: str | None) -> str | None:
    """Convierte string vacío/whitespace a None para que el resolver caiga en
    plantilla. Cualquier valor con contenido se conserva como override."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


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
    row.meta_title = _normalize_optional(body.meta_title)
    row.meta_description = _normalize_optional(body.meta_description)
    row.h1 = _normalize_optional(body.h1)
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


# --------------------------------------------------------------------------- #
# Bulk ops sobre seo_content
# --------------------------------------------------------------------------- #
def _load_seo_rows(db: Session, ids: list[int]) -> tuple[list[SeoContent], list[int]]:
    if not ids:
        return [], []
    rows = db.query(SeoContent).filter(SeoContent.id.in_(ids)).all()
    found = {r.id for r in rows}
    skipped = [i for i in ids if i not in found]
    return rows, skipped


@router.post("/seo/bulk-publish", response_model=BulkResultOut)
def bulk_publish_seo(
    body: BulkIdsIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> BulkResultOut:
    rows, skipped = _load_seo_rows(db, body.ids)
    now = datetime.now(timezone.utc)
    for r in rows:
        if r.reviewed_at is None:
            r.reviewed_at = now
        r.published = True
    db.commit()
    return BulkResultOut(updated=len(rows), skipped=skipped)


@router.post("/seo/bulk-unpublish", response_model=BulkResultOut)
def bulk_unpublish_seo(
    body: BulkIdsIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> BulkResultOut:
    rows, skipped = _load_seo_rows(db, body.ids)
    for r in rows:
        r.published = False
    db.commit()
    return BulkResultOut(updated=len(rows), skipped=skipped)


@router.post("/seo/bulk-mark-reviewed", response_model=BulkResultOut)
def bulk_mark_reviewed_seo(
    body: BulkIdsIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> BulkResultOut:
    rows, skipped = _load_seo_rows(db, body.ids)
    now = datetime.now(timezone.utc)
    for r in rows:
        if r.reviewed_at is None:
            r.reviewed_at = now
    db.commit()
    return BulkResultOut(updated=len(rows), skipped=skipped)


@router.post("/seo/bulk-delete", response_model=BulkResultOut)
def bulk_delete_seo(
    body: BulkIdsIn,
    confirm: bool = False,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> BulkResultOut:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="bulk-delete requiere ?confirm=true",
        )
    rows, skipped = _load_seo_rows(db, body.ids)
    for r in rows:
        db.delete(r)
    db.commit()
    return BulkResultOut(updated=len(rows), skipped=skipped)


# --------------------------------------------------------------------------- #
# CRUD de seo_templates
# --------------------------------------------------------------------------- #
def _template_to_out(t: SeoTemplate) -> SeoTemplateOut:
    return SeoTemplateOut(
        id=t.id,
        entity_type=t.entity_type,
        kind=t.kind,
        field=t.field,
        template=t.template,
        notes=t.notes,
        updated_at=t.updated_at,
    )


@router.get("/seo-templates", response_model=list[SeoTemplateOut])
def list_seo_templates(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[SeoTemplateOut]:
    rows = (
        db.query(SeoTemplate)
        .order_by(SeoTemplate.entity_type, SeoTemplate.kind.nulls_first(), SeoTemplate.field)
        .all()
    )
    return [_template_to_out(r) for r in rows]


@router.put("/seo-templates", response_model=SeoTemplateOut)
def upsert_seo_template(
    body: SeoTemplateIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> SeoTemplateOut:
    """Upsert por (entity_type, kind, field). kind NULL es válido."""
    kind = body.kind if body.kind else None
    q = db.query(SeoTemplate).filter(
        SeoTemplate.entity_type == body.entity_type,
        SeoTemplate.field == body.field,
    )
    q = q.filter(SeoTemplate.kind.is_(None)) if kind is None else q.filter(SeoTemplate.kind == kind)
    row = q.first()
    if row:
        row.template = body.template
        row.notes = body.notes
        row.updated_at = datetime.now(timezone.utc)
    else:
        row = SeoTemplate(
            entity_type=body.entity_type,
            kind=kind,
            field=body.field,
            template=body.template,
            notes=body.notes,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return _template_to_out(row)


@router.delete("/seo-templates/{template_id}", response_model=BulkResultOut)
def delete_seo_template(
    template_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> BulkResultOut:
    row = db.query(SeoTemplate).filter(SeoTemplate.id == template_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="template no encontrado")
    db.delete(row)
    db.commit()
    return BulkResultOut(updated=1, skipped=[])


@router.post("/seo-templates/preview", response_model=TemplatePreviewOut)
def preview_seo_template(
    body: TemplatePreviewIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> TemplatePreviewOut:
    """Renderiza una plantilla candidata contra una entidad de muestra (sin
    persistir nada). Útil para mostrar un preview en el panel de templates."""
    if body.entity_type == "artist":
        a = (
            db.query(Artist).filter(Artist.id == body.sample_entity_id).first()
            if body.sample_entity_id
            else db.query(Artist).order_by(Artist.id).first()
        )
        if not a:
            raise HTTPException(status_code=404, detail="sin artists para preview")
        ctx = {"name": a.name, "slug": a.slug}
        label = a.name
    elif body.entity_type == "album":
        q = db.query(Album)
        if body.kind:
            q = q.filter(Album.kind == body.kind)
        al = (
            q.filter(Album.id == body.sample_entity_id).first()
            if body.sample_entity_id
            else q.order_by(Album.id).first()
        )
        if not al:
            raise HTTPException(status_code=404, detail="sin albums para preview")
        ctx = {
            "title": al.title,
            "slug": al.slug,
            "year": str(al.year),
            "kind": al.kind,
            "artist": al.artist.name,
        }
        label = f"{al.artist.name} · {al.title}"
    else:  # song
        s = (
            db.query(Song).filter(Song.id == body.sample_entity_id).first()
            if body.sample_entity_id
            else db.query(Song).order_by(Song.id).first()
        )
        if not s:
            raise HTTPException(status_code=404, detail="sin songs para preview")
        al = s.album
        ctx = {
            "title": s.title,
            "slug": s.slug,
            "album": al.title,
            "artist": al.artist.name,
            "year": str(al.year),
            "kind": al.kind,
        }
        label = f"{al.artist.name} · {al.title} · {s.title}"

    rendered = render_with_context(body.template, ctx)
    return TemplatePreviewOut(rendered=rendered, context=ctx, sample_entity_label=label)


# --------------------------------------------------------------------------- #
# Users (read-only por ahora)
# --------------------------------------------------------------------------- #
class UserListItem(BaseModel):
    id: int
    email: str
    is_admin: bool
    is_active: bool
    email_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/users", response_model=list[UserListItem])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[UserListItem]:
    """Lista de usuarios registrados, orden por created_at desc."""
    rows = db.query(User).order_by(User.created_at.desc()).all()
    return [
        UserListItem(
            id=u.id,
            email=u.email,
            is_admin=u.is_admin,
            is_active=u.is_active,
            email_verified=u.email_verified_at is not None,
            created_at=u.created_at,
        )
        for u in rows
    ]


# --------------------------------------------------------------------------- #
# Posts del blog: revisión y publicación (Fase 3)
# --------------------------------------------------------------------------- #
from datetime import datetime as _dt, timezone as _tz  # noqa: E402

from app.db.models import Post as _Post  # noqa: E402


class AdminPostListItem(BaseModel):
    id: int
    slug: str
    kind: str
    status: str
    title: str
    excerpt: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    created_at: datetime
    published_at: datetime | None = None


class AdminPostDetailOut(AdminPostListItem):
    body_md: str
    meta_title: str | None = None
    meta_description: str | None = None
    hero_image_url: str | None = None


class AdminPostUpdateIn(BaseModel):
    title: str | None = None
    excerpt: str | None = None
    body_md: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None


@router.get("/posts", response_model=list[AdminPostListItem])
def admin_posts_list(
    status: str | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[AdminPostListItem]:
    q = db.query(_Post)
    if status and status != "all":
        q = q.filter(_Post.status == status)
    q = q.order_by(_Post.created_at.desc())
    rows = q.all()
    return [
        AdminPostListItem(
            id=p.id, slug=p.slug, kind=p.kind, status=p.status,
            title=p.title, excerpt=p.excerpt,
            source_url=p.source_url, source_name=p.source_name,
            created_at=p.created_at, published_at=p.published_at,
        )
        for p in rows
    ]


@router.get("/posts/{post_id}", response_model=AdminPostDetailOut)
def admin_post_detail(
    post_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminPostDetailOut:
    p = db.query(_Post).filter(_Post.id == post_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="post not found")
    return AdminPostDetailOut(
        id=p.id, slug=p.slug, kind=p.kind, status=p.status,
        title=p.title, excerpt=p.excerpt, body_md=p.body_md,
        meta_title=p.meta_title, meta_description=p.meta_description,
        hero_image_url=p.hero_image_url,
        source_url=p.source_url, source_name=p.source_name,
        created_at=p.created_at, published_at=p.published_at,
    )


@router.put("/posts/{post_id}", response_model=AdminPostDetailOut)
def admin_post_update(
    post_id: int,
    body: AdminPostUpdateIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminPostDetailOut:
    p = db.query(_Post).filter(_Post.id == post_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="post not found")
    if body.title is not None:
        p.title = body.title
    if body.excerpt is not None:
        p.excerpt = body.excerpt
    if body.body_md is not None:
        p.body_md = body.body_md
    if body.meta_title is not None:
        p.meta_title = body.meta_title
    if body.meta_description is not None:
        p.meta_description = body.meta_description
    db.commit()
    return admin_post_detail(post_id, db, _admin)


@router.post("/posts/{post_id}/publish", response_model=AdminPostListItem)
def admin_post_publish(
    post_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminPostListItem:
    """Publica el post (status='published', published_at=now). El cron de
    newsletter recogerá esta entrada en su próximo run y la enviará a los
    suscriptores."""
    p = db.query(_Post).filter(_Post.id == post_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="post not found")
    p.status = "published"
    if p.published_at is None:
        p.published_at = _dt.now(_tz.utc)
    p.approved_by = _admin.id
    db.commit()
    return AdminPostListItem(
        id=p.id, slug=p.slug, kind=p.kind, status=p.status,
        title=p.title, excerpt=p.excerpt,
        source_url=p.source_url, source_name=p.source_name,
        created_at=p.created_at, published_at=p.published_at,
    )


@router.post("/posts/{post_id}/reject", response_model=AdminPostListItem)
def admin_post_reject(
    post_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminPostListItem:
    p = db.query(_Post).filter(_Post.id == post_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="post not found")
    p.status = "rejected"
    p.approved_by = _admin.id
    db.commit()
    return AdminPostListItem(
        id=p.id, slug=p.slug, kind=p.kind, status=p.status,
        title=p.title, excerpt=p.excerpt,
        source_url=p.source_url, source_name=p.source_name,
        created_at=p.created_at, published_at=p.published_at,
    )


@router.post("/posts/{post_id}/unpublish", response_model=AdminPostListItem)
def admin_post_unpublish(
    post_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminPostListItem:
    p = db.query(_Post).filter(_Post.id == post_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="post not found")
    p.status = "approved"  # vuelve a aprobado pero no publicado
    db.commit()
    return AdminPostListItem(
        id=p.id, slug=p.slug, kind=p.kind, status=p.status,
        title=p.title, excerpt=p.excerpt,
        source_url=p.source_url, source_name=p.source_name,
        created_at=p.created_at, published_at=p.published_at,
    )


# --------------------------------------------------------------------------- #
# Subscribers (newsletter) — listado y acciones de mantenimiento
# --------------------------------------------------------------------------- #
from app.db.models import Subscriber as _Subscriber  # noqa: E402


class AdminSubscriberListItem(BaseModel):
    id: int
    email: str
    status: str
    source: str | None = None
    subscribed_at: datetime
    confirmed_at: datetime | None = None
    unsubscribed_at: datetime | None = None
    last_sent_at: datetime | None = None


class AdminSubscriberStats(BaseModel):
    pending: int
    confirmed: int
    unsubscribed: int
    bounced: int
    total: int


@router.get("/subscribers/stats", response_model=AdminSubscriberStats)
def admin_subscribers_stats(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminSubscriberStats:
    rows = (
        db.query(_Subscriber.status, func.count(_Subscriber.id))
        .group_by(_Subscriber.status)
        .all()
    )
    counts = {status: int(n) for status, n in rows}
    return AdminSubscriberStats(
        pending=counts.get("pending", 0),
        confirmed=counts.get("confirmed", 0),
        unsubscribed=counts.get("unsubscribed", 0),
        bounced=counts.get("bounced", 0),
        total=sum(counts.values()),
    )


@router.get("/subscribers", response_model=list[AdminSubscriberListItem])
def admin_subscribers_list(
    status: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[AdminSubscriberListItem]:
    query = db.query(_Subscriber)
    if status and status != "all":
        query = query.filter(_Subscriber.status == status)
    if q:
        query = query.filter(_Subscriber.email.ilike(f"%{q.strip()}%"))
    query = query.order_by(_Subscriber.subscribed_at.desc()).offset(offset).limit(limit)
    rows = query.all()
    return [
        AdminSubscriberListItem(
            id=s.id,
            email=s.email,
            status=s.status,
            source=s.source,
            subscribed_at=s.subscribed_at,
            confirmed_at=s.confirmed_at,
            unsubscribed_at=s.unsubscribed_at,
            last_sent_at=s.last_sent_at,
        )
        for s in rows
    ]


@router.post("/subscribers/{sub_id}/resend-confirmation", response_model=AdminSubscriberListItem)
def admin_subscribers_resend(
    sub_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminSubscriberListItem:
    s = db.query(_Subscriber).filter(_Subscriber.id == sub_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="subscriber not found")
    if s.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"solo pending puede reenviarse (actual: {s.status})",
        )
    from app.services.email import (
        EmailError,
        render_newsletter_confirm_email,
        send_email,
    )
    site_url = os.environ.get("SITE_URL", "https://entreinteriores.com").rstrip("/")
    confirm_url = f"{site_url}/newsletter/confirmar?token={s.confirm_token}"
    html, text = render_newsletter_confirm_email(confirm_url)
    try:
        send_email(
            to=s.email,
            subject="Confirma tu suscripción · Entre Interiores",
            html=html,
            text=text,
        )
    except EmailError as exc:
        raise HTTPException(status_code=502, detail=f"email failed: {exc}") from exc
    return AdminSubscriberListItem(
        id=s.id, email=s.email, status=s.status, source=s.source,
        subscribed_at=s.subscribed_at, confirmed_at=s.confirmed_at,
        unsubscribed_at=s.unsubscribed_at, last_sent_at=s.last_sent_at,
    )


@router.post("/subscribers/{sub_id}/mark-bounced", response_model=AdminSubscriberListItem)
def admin_subscribers_mark_bounced(
    sub_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminSubscriberListItem:
    s = db.query(_Subscriber).filter(_Subscriber.id == sub_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="subscriber not found")
    s.status = "bounced"
    db.commit()
    return AdminSubscriberListItem(
        id=s.id, email=s.email, status=s.status, source=s.source,
        subscribed_at=s.subscribed_at, confirmed_at=s.confirmed_at,
        unsubscribed_at=s.unsubscribed_at, last_sent_at=s.last_sent_at,
    )


@router.delete("/subscribers/{sub_id}", response_model=BulkResultOut)
def admin_subscribers_delete(
    sub_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> BulkResultOut:
    s = db.query(_Subscriber).filter(_Subscriber.id == sub_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="subscriber not found")
    db.delete(s)
    db.commit()
    return BulkResultOut(affected=1, errors=[])


# --------------------------------------------------------------------------- #
# Banco de propuestas editoriales (content_proposals) + calendario
# --------------------------------------------------------------------------- #
from datetime import date as _date, timedelta as _timedelta  # noqa: E402

from app.db.models import ContentProposal as _Proposal  # noqa: E402

# Tope de publicaciones por semana natural (lunes-domingo).
WEEKLY_PUBLISH_CAP = 2


class AdminProposalItem(BaseModel):
    id: int
    kind: str
    source_type: str | None = None
    source_id: int | None = None
    title: str
    angle: str | None = None
    status: str
    scheduled_for: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    has_body: bool = False
    keywords: list[dict] = []
    keyword_volume: int = 0  # volumen agregado, para ordenar
    created_at: datetime


class AdminProposalStats(BaseModel):
    proposed: int
    scheduled: int
    used: int
    discarded: int


class ScheduleProposalIn(BaseModel):
    date: str  # YYYY-MM-DD


def _week_bounds(d: _date) -> tuple[_date, _date]:
    """Lunes y domingo de la semana natural que contiene `d`."""
    monday = d - _timedelta(days=d.weekday())
    return monday, monday + _timedelta(days=6)


def _proposal_to_item(p: _Proposal) -> AdminProposalItem:
    kws = p.keywords or []
    return AdminProposalItem(
        id=p.id,
        kind=p.kind,
        source_type=p.source_type,
        source_id=p.source_id,
        title=p.title,
        angle=p.angle,
        status=p.status,
        scheduled_for=p.scheduled_for.isoformat() if p.scheduled_for else None,
        source_url=p.source_url,
        source_name=p.source_name,
        has_body=bool(p.body_md),
        keywords=kws,
        keyword_volume=sum(int(k.get("volume") or 0) for k in kws),
        created_at=p.created_at,
    )


@router.get("/proposals/stats", response_model=AdminProposalStats)
def admin_proposals_stats(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminProposalStats:
    rows = (
        db.query(_Proposal.status, func.count(_Proposal.id))
        .group_by(_Proposal.status)
        .all()
    )
    c = {s: int(n) for s, n in rows}
    return AdminProposalStats(
        proposed=c.get("proposed", 0),
        scheduled=c.get("scheduled", 0),
        used=c.get("used", 0),
        discarded=c.get("discarded", 0),
    )


@router.get("/proposals", response_model=list[AdminProposalItem])
def admin_proposals_list(
    status: str | None = None,
    kind: str | None = None,
    limit: int = 500,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[AdminProposalItem]:
    q = db.query(_Proposal)
    if status and status != "all":
        q = q.filter(_Proposal.status == status)
    if kind and kind != "all":
        q = q.filter(_Proposal.kind == kind)
    # Orden: primero actualidad (news, aniversarios), luego repositorio.
    kind_order = {
        "news": 0, "anniversary": 1, "album-anniversary": 2,
        "spotlight": 3, "evergreen": 4,
    }
    rows = q.order_by(_Proposal.created_at.desc()).limit(min(limit, 1000)).all()
    rows.sort(key=lambda p: (kind_order.get(p.kind, 9), p.created_at))
    return [_proposal_to_item(p) for p in rows]


@router.post("/proposals/{proposal_id}/schedule", response_model=AdminProposalItem)
def admin_proposal_schedule(
    proposal_id: int,
    payload: ScheduleProposalIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminProposalItem:
    p = db.query(_Proposal).filter(_Proposal.id == proposal_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="proposal not found")
    if p.status in ("used", "discarded"):
        raise HTTPException(
            status_code=409, detail=f"propuesta en estado {p.status}, no programable"
        )
    try:
        target = _date.fromisoformat(payload.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="fecha inválida (YYYY-MM-DD)")
    if target < _date.today():
        raise HTTPException(status_code=400, detail="la fecha ya pasó")

    # Validación del cap: máximo WEEKLY_PUBLISH_CAP por semana natural.
    monday, sunday = _week_bounds(target)
    week_count = (
        db.query(func.count(_Proposal.id))
        .filter(_Proposal.status == "scheduled")
        .filter(_Proposal.scheduled_for >= monday)
        .filter(_Proposal.scheduled_for <= sunday)
        .filter(_Proposal.id != p.id)
        .scalar()
    )
    if week_count >= WEEKLY_PUBLISH_CAP:
        raise HTTPException(
            status_code=409,
            detail=(
                f"La semana del {monday.isoformat()} ya tiene "
                f"{WEEKLY_PUBLISH_CAP} publicaciones programadas."
            ),
        )

    p.status = "scheduled"
    p.scheduled_for = target
    db.commit()
    db.refresh(p)
    return _proposal_to_item(p)


@router.post("/proposals/{proposal_id}/unschedule", response_model=AdminProposalItem)
def admin_proposal_unschedule(
    proposal_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminProposalItem:
    p = db.query(_Proposal).filter(_Proposal.id == proposal_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="proposal not found")
    if p.status != "scheduled":
        raise HTTPException(status_code=409, detail="la propuesta no está programada")
    p.status = "proposed"
    p.scheduled_for = None
    db.commit()
    db.refresh(p)
    return _proposal_to_item(p)


@router.post("/proposals/{proposal_id}/discard", response_model=AdminProposalItem)
def admin_proposal_discard(
    proposal_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminProposalItem:
    p = db.query(_Proposal).filter(_Proposal.id == proposal_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="proposal not found")
    if p.status == "used":
        raise HTTPException(status_code=409, detail="propuesta ya usada")
    p.status = "discarded"
    p.scheduled_for = None
    db.commit()
    db.refresh(p)
    return _proposal_to_item(p)
