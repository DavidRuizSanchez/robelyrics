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
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import (
    Album,
    Artist,
    Band,
    Concept,
    InterpretationSource,
    Person,
    Place,
    SeoContent,
    SeoTemplate,
    Song,
    Theme,
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
    if entity_type == "person":
        p = db.query(Person).filter(Person.id == entity_id).first()
        if not p:
            return ("?", "")
        return (p.stage_name or p.full_name, f"/personas/{p.slug}")
    if entity_type == "band":
        b = db.query(Band).filter(Band.id == entity_id).first()
        if not b:
            return ("?", "")
        base = "/sellos" if b.kind == "label" else "/grupos"
        return (b.name, f"{base}/{b.slug}")
    if entity_type == "theme":
        t = db.query(Theme).filter(Theme.id == entity_id).first()
        if not t:
            return ("?", "")
        return (t.name, f"/temas/{t.slug}")
    if entity_type == "place":
        pl = db.query(Place).filter(Place.id == entity_id).first()
        if not pl:
            return ("?", "")
        return (pl.name, f"/lugares/{pl.slug}")
    if entity_type == "concept":
        c = db.query(Concept).filter(Concept.id == entity_id).first()
        if not c:
            return ("?", "")
        return (c.name, f"/conceptos/{c.slug}")
    return ("?", "")


@router.get("/seo", response_model=list[SeoContentListItem])
def list_seo(
    status: Literal["all", "unreviewed", "reviewed", "published"] = "all",
    entity_type: Literal[
        "all", "artist", "album", "song", "person", "band", "theme", "place", "concept"
    ] = "all",
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[SeoContentListItem]:
    q = db.query(SeoContent)
    if status == "unreviewed":
        # "Sin revisar" = pendiente de revisión: ni revisado ni publicado.
        # (Hay filas publicadas por el script de generación con reviewed_at=NULL;
        #  no deben colarse aquí.)
        q = q.filter(SeoContent.reviewed_at.is_(None), SeoContent.published.is_(False))
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
        # Coalesce a "" cuando no hay override ni plantilla para el
        # (entity_type, field) — p.ej. person/band/theme/place/concept sin
        # plantilla SEO. El frontend los usa como placeholder del editor.
        resolved_title=resolved["title"] or "",
        resolved_description=resolved["description"] or "",
        resolved_h1=resolved["h1"] or "",
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
    scheduled_for: datetime | None = None


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
            scheduled_for=p.scheduled_for,
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


class AdminPostScheduleIn(BaseModel):
    # Fecha (o fecha-hora) ISO en la que se publicará. "YYYY-MM-DD" → 00:00 UTC.
    scheduled_for: str


@router.post("/posts/{post_id}/schedule", response_model=AdminPostListItem)
def admin_post_schedule(
    post_id: int,
    body: AdminPostScheduleIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminPostListItem:
    """Programa el post para publicarse en una fecha futura. El cron diario
    `flush_scheduled_due` lo promueve a `published` cuando llega `scheduled_for`
    (respetando el cap móvil de 2/semana para kinds no exentos)."""
    p = db.query(_Post).filter(_Post.id == post_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="post not found")
    try:
        when = _dt.fromisoformat(body.scheduled_for)
    except ValueError:
        raise HTTPException(status_code=400, detail="fecha inválida (usa YYYY-MM-DD)")
    if when.tzinfo is None:
        when = when.replace(tzinfo=_tz.utc)
    now = _dt.now(_tz.utc)
    # Permite hoy (se publicará en el próximo run del cron); rechaza ayer o antes.
    if when.date() < now.date():
        raise HTTPException(status_code=400, detail="la fecha ya pasó")
    p.status = "scheduled"
    p.scheduled_for = when
    p.approved_by = _admin.id
    db.commit()
    return AdminPostListItem(
        id=p.id, slug=p.slug, kind=p.kind, status=p.status,
        title=p.title, excerpt=p.excerpt,
        source_url=p.source_url, source_name=p.source_name,
        created_at=p.created_at, published_at=p.published_at,
    )


@router.post("/posts/{post_id}/unschedule", response_model=AdminPostListItem)
def admin_post_unschedule(
    post_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminPostListItem:
    """Desprograma: vuelve a pending_review para revisar/editar/publicar a mano."""
    p = db.query(_Post).filter(_Post.id == post_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="post not found")
    p.status = "pending_review"
    p.scheduled_for = None
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

from app.db.models import (  # noqa: E402
    ContentProposal as _Proposal,
    UrlIngestJob as _IngestJob,
)
from app.services import url_ingest  # noqa: E402
from app.services.publishing import (  # noqa: E402
    EVENT_LEAD_DAYS,
    PUBLISH_SLOT_DAYS,
    WEEKLY_CAP as WEEKLY_PUBLISH_CAP,
)


class AdminProposalItem(BaseModel):
    id: int
    kind: str
    source_type: str | None = None
    source_id: int | None = None
    title: str
    angle: str | None = None
    status: str
    scheduled_for: str | None = None
    recommended_for: str | None = None  # fecha sugerida (efemérides / evento−3d)
    event_date: str | None = None       # fecha real del evento (si la hay)
    force_publish: bool = False          # override "publicar sí o sí"
    has_video: bool = False              # lleva vídeo embebido
    source_url: str | None = None
    source_name: str | None = None
    has_body: bool = False
    keywords: list[dict] = []
    keyword_volume: int = 0  # volumen agregado, para ordenar
    target_keyword: str | None = None
    search_volume: int | None = None
    is_longtail: bool = False
    signal_source: str | None = None
    created_at: datetime


class AdminProposalDetail(AdminProposalItem):
    """Detalle para revisión: incluye el cuerpo (si ya está generado)."""
    body_md: str | None = None
    excerpt: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    content_key: str | None = None


class AdminProposalStats(BaseModel):
    proposed: int
    approved: int
    scheduled: int
    used: int
    discarded: int
    # Conteo por estado y tipo: {status: {kind: n}}. Para los filtros por tipo.
    by_kind: dict[str, dict[str, int]] = {}


class ScheduleProposalIn(BaseModel):
    date: str  # YYYY-MM-DD
    replace: bool = False  # confirmar reemplazo si hay conflicto (avisos del front)


class ProposalFromUrlIn(BaseModel):
    """Alta MANUAL de una propuesta de blog a partir de una URL.

    El admin pega un enlace y entra al banco como `kind='news'`, estado
    `proposed`, igual que las del agregador automático: se revisa, aprueba y
    programa desde el mismo panel. Con `rewrite` (por defecto) pasa por la
    misma investigación + voz editorial + verificación factual que las
    noticias del cron; sin él, guarda el texto scrapeado tal cual.

    `body_text` es la salida para los medios que bloquean la descarga desde el
    server (WAF que responde 406/403 a cualquier UA que no sea navegador, muros
    de pago, artículos montados por JS): el admin abre el artículo, copia el
    texto y lo pega. Si viene, se usa en vez de descargar — el resto del
    pipeline (voz editorial, fact-check, dedup) corre igual.
    """

    url: str
    topic: str | None = None  # pista del tema (si el título no basta)
    body_text: str | None = None  # texto pegado a mano si el scrape no puede
    rewrite: bool = True       # voz editorial + investigación + fact-check
    force: bool = False        # salta el dedup por tema (no el de URL exacta)

    @field_validator("url")
    @classmethod
    def _block_ssrf(cls, v: str) -> str:
        return _validate_external_url(v)


class UrlIngestJobOut(BaseModel):
    """Estado de un alta manual. El trabajo tarda minutos y corre en segundo
    plano, así que el panel pregunta por él hasta que deja de estar `running`."""

    id: int
    status: str  # running | done | rejected | failed
    url: str
    # done
    proposal_id: int | None = None
    title: str | None = None
    rewritten: bool = False
    warning: str | None = None
    # rejected (veredicto del editor jefe)
    score: int | None = None
    reasons: list[str] = []
    boosted: bool = False
    # failed
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


def _job_to_out(j: "_IngestJob") -> UrlIngestJobOut:
    return UrlIngestJobOut(
        id=j.id,
        status=j.status,
        url=j.url,
        proposal_id=j.proposal_id,
        title=j.title,
        rewritten=bool(j.rewritten),
        warning=j.warning,
        score=j.score,
        reasons=list(j.reasons or []),
        boosted=bool(j.boosted),
        error=j.error,
        created_at=j.created_at,
        finished_at=j.finished_at,
    )


class TitleCandidate(BaseModel):
    title: str
    meta_title: str


class SuggestTitlesOut(BaseModel):
    candidates: list[TitleCandidate]


class SetTitleIn(BaseModel):
    title: str
    meta_title: str | None = None


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
        recommended_for=(
            p.recommended_date.isoformat()
            if getattr(p, "recommended_date", None)
            else None
        ),
        event_date=(
            p.event_date.isoformat()
            if getattr(p, "event_date", None)
            else None
        ),
        force_publish=bool(getattr(p, "force_publish", False)),
        has_video=bool(getattr(p, "video", None)),
        source_url=p.source_url,
        source_name=p.source_name,
        has_body=bool(p.body_md),
        keywords=kws,
        keyword_volume=sum(int(k.get("volume") or 0) for k in kws),
        target_keyword=getattr(p, "target_keyword", None),
        search_volume=getattr(p, "search_volume", None),
        is_longtail=bool(getattr(p, "is_longtail", False)),
        signal_source=getattr(p, "signal_source", None),
        created_at=p.created_at,
    )


@router.get("/proposals/stats", response_model=AdminProposalStats)
def admin_proposals_stats(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminProposalStats:
    rows = (
        db.query(_Proposal.status, _Proposal.kind, func.count(_Proposal.id))
        .group_by(_Proposal.status, _Proposal.kind)
        .all()
    )
    totals: dict[str, int] = {}
    by_kind: dict[str, dict[str, int]] = {}
    for status, kind, n in rows:
        totals[status] = totals.get(status, 0) + int(n)
        by_kind.setdefault(status, {})[kind] = int(n)
    return AdminProposalStats(
        proposed=totals.get("proposed", 0),
        approved=totals.get("approved", 0),
        scheduled=totals.get("scheduled", 0),
        used=totals.get("used", 0),
        discarded=totals.get("discarded", 0),
        by_kind=by_kind,
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


@router.get("/proposals/{proposal_id}", response_model=AdminProposalDetail)
def admin_proposal_detail(
    proposal_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminProposalDetail:
    """Detalle de una propuesta para revisarla (incluye el cuerpo si existe)."""
    p = db.query(_Proposal).filter(_Proposal.id == proposal_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="proposal not found")
    base = _proposal_to_item(p)
    return AdminProposalDetail(
        **base.model_dump(),
        body_md=p.body_md,
        excerpt=p.excerpt,
        meta_title=p.meta_title,
        meta_description=p.meta_description,
        content_key=p.content_key,
    )


@router.post("/proposals/{proposal_id}/approve", response_model=AdminProposalItem)
def admin_proposal_approve(
    proposal_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminProposalItem:
    """Valida una propuesta: `proposed`/`scheduled` → `approved` (sin fecha).
    Al aprobar se genera el borrador de forma SÍNCRONA (cuerpo RAG + foto +
    saneado), salvo que ya tenga cuerpo (noticias). Puede tardar ~1 min. Si la
    generación falla, queda `approved` sin cuerpo y el cron
    `generate_approved_drafts` reintenta."""
    import logging

    from app.services.draft_generator import generate_proposal_draft

    p = db.query(_Proposal).filter(_Proposal.id == proposal_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="proposal not found")
    if p.status in ("used", "discarded"):
        raise HTTPException(
            status_code=409, detail=f"propuesta en estado {p.status}, no aprobable"
        )
    p.status = "approved"
    p.scheduled_for = None
    db.commit()
    db.refresh(p)

    if not p.body_md:
        try:
            generate_proposal_draft(db, p)
            db.refresh(p)
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception(
                "Generación de borrador falló al aprobar propuesta %s; "
                "el cron de respaldo reintentará",
                p.id,
            )
    return _proposal_to_item(p)


class BulkApproveIn(BaseModel):
    ids: list[int]


@router.post("/proposals/bulk-approve")
def admin_proposals_bulk_approve(
    payload: BulkApproveIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> dict:
    """Aprueba en bloque SIN generar los borradores (respuesta inmediata).
    Marca las propuestas como `approved`; el cron `generate_approved_drafts`
    (cada 5 min) genera el cuerpo RAG de las que no lo traen. Las noticias ya
    tienen cuerpo del scraper, así que quedan listas al momento. Evita el
    cuello de botella de generar uno a uno de forma síncrona."""
    if not payload.ids:
        raise HTTPException(status_code=400, detail="lista de ids vacía")
    rows = (
        db.query(_Proposal)
        .filter(_Proposal.id.in_(payload.ids))
        .filter(_Proposal.status == "proposed")
        .all()
    )
    for p in rows:
        p.status = "approved"
        p.scheduled_for = None
    db.commit()
    pending_draft = sum(1 for p in rows if not p.body_md)
    return {"approved": len(rows), "pending_draft": pending_draft}


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

    # Conflictos (se avisan al front; `replace=True` los confirma):
    #   1) esta propuesta YA tenía fecha,
    #   2) ese día/semana ya está ocupado (tope semanal),
    #   3) la fecha cae el día del evento o después (se publicaría tarde).
    conflicts: list[str] = []
    if p.status == "scheduled" and p.scheduled_for and p.scheduled_for != target:
        conflicts.append(f"ya estaba programada para {p.scheduled_for.isoformat()}")

    monday, sunday = _week_bounds(target)
    same_day = (
        db.query(func.count(_Proposal.id))
        .filter(_Proposal.status == "scheduled")
        .filter(_Proposal.scheduled_for == target)
        .filter(_Proposal.id != p.id)
        .scalar()
    )
    if same_day:
        conflicts.append(f"el {target.isoformat()} ya tiene otra publicación")
    week_count = (
        db.query(func.count(_Proposal.id))
        .filter(_Proposal.status == "scheduled")
        .filter(_Proposal.scheduled_for >= monday)
        .filter(_Proposal.scheduled_for <= sunday)
        .filter(_Proposal.id != p.id)
        .scalar()
    )
    if week_count >= WEEKLY_PUBLISH_CAP:
        conflicts.append(
            f"la semana del {monday.isoformat()} ya tiene {WEEKLY_PUBLISH_CAP}"
        )
    if p.event_date and target >= p.event_date:
        conflicts.append(
            f"el evento es el {p.event_date.isoformat()}: se publicaría tarde"
        )

    if conflicts and not payload.replace:
        raise HTTPException(
            status_code=409,
            detail=" · ".join(conflicts) + " — confirma para reemplazar/forzar",
        )

    p.status = "scheduled"
    p.scheduled_for = target
    db.commit()
    db.refresh(p)
    return _proposal_to_item(p)


class AutoScheduleIn(BaseModel):
    # Si `ids` viene vacío/None, se auto-programan TODAS las aprobadas.
    ids: list[int] | None = None
    weeks: int = 4  # ventana temporal: próximas N semanas


class BulkScheduleResult(BaseModel):
    scheduled: list[dict] = []   # [{id, date}]
    skipped: list[dict] = []     # [{id, reason}]


_ACTUALIDAD_KINDS = {"news", "anniversary", "album-anniversary"}


def _interleave_by_type(proposals: list[_Proposal]) -> list[_Proposal]:
    """Ordena intercalando tipos para que no salgan dos del mismo tipo
    seguidos. Buckets por prioridad: actualidad → spotlight → evergreen.
    Round-robin tomando uno de cada bucket por ronda (prioriza actualidad)."""
    buckets: dict[int, list[_Proposal]] = {0: [], 1: [], 2: []}
    for p in proposals:
        if p.kind in _ACTUALIDAD_KINDS:
            buckets[0].append(p)
        elif p.kind == "spotlight":
            buckets[1].append(p)
        else:
            buckets[2].append(p)
    ordered: list[_Proposal] = []
    while any(buckets.values()):
        for b in (0, 1, 2):
            if buckets[b]:
                ordered.append(buckets[b].pop(0))
    return ordered


@router.post("/proposals/auto-schedule", response_model=BulkScheduleResult)
def admin_proposals_auto_schedule(
    payload: AutoScheduleIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> BulkScheduleResult:
    """Auto-programa propuestas en las próximas `weeks` semanas teniendo en
    cuenta las FECHAS:
      - efemérides (aniversarios) → su día exacto (recommended_date).
      - eventos (event_date) → un slot martes/jueves/sábado con ≥EVENT_LEAD_DAYS
        días de antelación; si no hay hueco antes del evento, se descarta.
      - resto → reparto normal intercalando tipos, máx WEEKLY_PUBLISH_CAP/semana.
    Si `ids` viene vacío, programa todas las aprobadas."""
    q = db.query(_Proposal)
    if payload.ids:
        q = q.filter(_Proposal.id.in_(payload.ids))
    else:
        q = q.filter(_Proposal.status == "approved")
    candidates = q.all()

    result = BulkScheduleResult()
    valid = [p for p in candidates if p.status in ("proposed", "approved")]
    if payload.ids:
        valid_ids = {p.id for p in valid}
        for p in candidates:
            if p.id not in valid_ids:
                result.skipped.append({"id": p.id, "reason": p.status})

    # Cuenta lo ya programado por semana (lunes natural → nº).
    week_counts: dict[_date, int] = {}
    for (sf,) in db.query(_Proposal.scheduled_for).filter(
        _Proposal.status == "scheduled", _Proposal.scheduled_for.isnot(None)
    ).all():
        if sf:
            mon, _ = _week_bounds(sf if isinstance(sf, _date) else sf.date())
            week_counts[mon] = week_counts.get(mon, 0) + 1

    today = _date.today()
    start_monday = today - _timedelta(days=today.weekday()) + _timedelta(days=7)
    last_monday = start_monday + _timedelta(days=7 * (max(payload.weeks, 1) - 1))

    def _assign(p: _Proposal, target: _date) -> None:
        p.status = "scheduled"
        p.scheduled_for = target
        mon, _ = _week_bounds(target)
        week_counts[mon] = week_counts.get(mon, 0) + 1
        result.scheduled.append({"id": p.id, "date": target.isoformat()})

    def _first_open_slot(not_after: _date | None = None) -> _date | None:
        """Primer slot Mar/Jue/Sáb con hueco semanal dentro de la ventana
        (opcionalmente, no más tarde de `not_after`)."""
        m = start_monday
        while m <= last_monday:
            n = week_counts.get(m, 0)
            if n < WEEKLY_PUBLISH_CAP:
                slot = PUBLISH_SLOT_DAYS[n] if n < len(PUBLISH_SLOT_DAYS) else 0
                target = m + _timedelta(days=slot)
                if not_after is None or target <= not_after:
                    return target
            m = m + _timedelta(days=7)
        return None

    # 1) EFEMÉRIDES: su día exacto (recommended_date), al margen del cap.
    ephem = [
        p for p in valid
        if p.kind in ("anniversary", "album-anniversary") and p.recommended_date
    ]
    for p in ephem:
        if p.recommended_date < today:
            result.skipped.append({"id": p.id, "reason": "efeméride ya pasó"})
            continue
        _assign(p, p.recommended_date)

    # 2) EVENTOS: slot con ≥EVENT_LEAD_DAYS de antelación al evento.
    events = [p for p in valid if p not in ephem and p.event_date]
    for p in events:
        deadline = p.event_date - _timedelta(days=EVENT_LEAD_DAYS)
        if deadline < start_monday + _timedelta(days=PUBLISH_SLOT_DAYS[0]):
            result.skipped.append({"id": p.id, "reason": "evento demasiado próximo/pasado"})
            continue
        target = _first_open_slot(not_after=deadline)
        if target is None:
            result.skipped.append({"id": p.id, "reason": "sin hueco antes del evento"})
            continue
        _assign(p, target)

    # 3) RESTO (sin fecha): reparto normal intercalando tipos.
    rest = [p for p in valid if p not in ephem and p not in events]
    for p in _interleave_by_type(rest):
        target = _first_open_slot()
        if target is None:
            result.skipped.append({"id": p.id, "reason": "ventana llena"})
            continue
        _assign(p, target)

    db.commit()
    return result


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
    # Quitar fecha la devuelve a "aprobada" (no a "proposed": ya está validada).
    p.status = "approved"
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


@router.post("/proposals/{proposal_id}/restore", response_model=AdminProposalItem)
def admin_proposal_restore(
    proposal_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminProposalItem:
    """Recupera una propuesta descartada: `discarded` → `proposed`."""
    p = db.query(_Proposal).filter(_Proposal.id == proposal_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="proposal not found")
    if p.status != "discarded":
        raise HTTPException(status_code=409, detail="la propuesta no está descartada")
    p.status = "proposed"
    db.commit()
    db.refresh(p)
    return _proposal_to_item(p)


@router.post("/proposals/{proposal_id}/force-publish", response_model=AdminProposalItem)
def admin_proposal_force_publish(
    proposal_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminProposalItem:
    """Conmuta el override 'publicar sí o sí': la propuesta se publicará aunque no
    pase el gate de calidad (rigor/longitud/foco). El fact-check canónico se
    mantiene."""
    p = db.query(_Proposal).filter(_Proposal.id == proposal_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="proposal not found")
    p.force_publish = not bool(p.force_publish)
    db.commit()
    db.refresh(p)
    return _proposal_to_item(p)


@router.post("/proposals/{proposal_id}/suggest-titles", response_model=SuggestTitlesOut)
@limiter.limit("60/hour")
def admin_proposal_suggest_titles(
    request: Request,
    proposal_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> SuggestTitlesOut:
    """Propone 3 titulares alternativos a partir del cuerpo ya escrito. No
    persiste nada: el panel muestra los candidatos y el admin guarda el que
    elija (o teclea el suyo)."""
    from app.services.news_research import suggest_titles

    p = db.query(_Proposal).filter(_Proposal.id == proposal_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="proposal not found")
    if not (p.body_md or "").strip():
        raise HTTPException(
            status_code=409,
            detail="la propuesta aún no tiene cuerpo; escribe el titular a mano",
        )
    subject = p.target_keyword or p.title
    candidates = suggest_titles(p.body_md, p.title, subject=subject, n=3)
    if not candidates:
        raise HTTPException(
            status_code=502, detail="no se han podido generar titulares; reintenta"
        )
    return SuggestTitlesOut(candidates=[TitleCandidate(**c) for c in candidates])


@router.post("/proposals/{proposal_id}/title", response_model=AdminProposalDetail)
def admin_proposal_set_title(
    proposal_id: int,
    payload: SetTitleIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminProposalDetail:
    """Guarda el titular (elegido de las sugerencias o tecleado a mano). Sanea
    el texto (anti em-dash + nunca 'Robe Iniesta'). NO recalcula `content_key`:
    cambiar el titular es un retoque editorial del mismo contenido ya
    deduplicado, así que la huella de evento se mantiene estable."""
    from app.services.text_sanitizer import enforce_name_policy, strip_ai_tells

    p = db.query(_Proposal).filter(_Proposal.id == proposal_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="proposal not found")
    if p.status in ("used", "discarded"):
        raise HTTPException(
            status_code=409,
            detail=f"propuesta en estado {p.status}, no editable",
        )

    title = (enforce_name_policy(strip_ai_tells(payload.title)) or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="el titular no puede estar vacío")
    p.title = title[:240]

    if payload.meta_title is not None:
        meta = (enforce_name_policy(strip_ai_tells(payload.meta_title)) or "").strip()
        p.meta_title = (meta or title)[:60]

    db.commit()
    db.refresh(p)
    base = _proposal_to_item(p)
    return AdminProposalDetail(
        **base.model_dump(),
        body_md=p.body_md,
        excerpt=p.excerpt,
        meta_title=p.meta_title,
        meta_description=p.meta_description,
        content_key=p.content_key,
    )


@router.post(
    "/proposals/from-url", response_model=UrlIngestJobOut, status_code=202
)
@limiter.limit("20/hour")
def admin_proposal_from_url(
    request: Request,
    body: ProposalFromUrlIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> UrlIngestJobOut:
    """ENCOLA el alta de una propuesta desde una URL y responde al momento (202).

    El trabajo real (investigación + voz editorial + verificación + gate de rigor)
    tarda de 2 a 4 minutos y Cloudflare corta a los 100 s, así que no cabe en la
    petición: lo ejecuta el servidor en segundo plano —sobrevive a cerrar la
    pestaña— y el panel consulta el estado con `GET /admin/ingest-jobs`.
    """
    job = _IngestJob(
        url=body.url,
        topic=body.topic,
        body_text=body.body_text,
        rewrite=body.rewrite,
        force=body.force,
        status="running",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    background.add_task(url_ingest.run_job, job.id)
    return _job_to_out(job)


@router.get("/ingest-jobs", response_model=list[UrlIngestJobOut])
def admin_ingest_jobs(
    limit: int = 5,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[UrlIngestJobOut]:
    """Últimos trabajos de alta manual. El panel lo consulta al cargar para
    recuperar lo que quedó corriendo cuando se cerró la pestaña."""
    # Huérfanos: el trabajo vive en el proceso de la API, así que un reinicio (un
    # deploy, sin ir más lejos) lo mata sin que nadie lo marque. Sin esto el panel
    # se quedaría girando para siempre. El techo real medido son ~4,5 min.
    stale = (
        db.query(_IngestJob)
        .filter(
            _IngestJob.status == "running",
            _IngestJob.created_at < datetime.now(timezone.utc) - _timedelta(minutes=15),
        )
        .all()
    )
    for j in stale:
        j.status = "failed"
        j.error = (
            "el trabajo se perdió (probablemente un reinicio del servidor); "
            "vuelve a intentarlo"
        )
        j.finished_at = datetime.now(timezone.utc)
    if stale:
        db.commit()

    rows = (
        db.query(_IngestJob)
        .order_by(_IngestJob.id.desc())
        .limit(max(1, min(limit, 20)))
        .all()
    )
    return [_job_to_out(j) for j in rows]


@router.get("/ingest-jobs/{job_id}", response_model=UrlIngestJobOut)
def admin_ingest_job(
    job_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> UrlIngestJobOut:
    job = db.get(_IngestJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="trabajo no encontrado")
    return _job_to_out(job)


# --------------------------------------------------------------------------- #
# Instagram (@entreinterioresrobe) — cola de publicación
# --------------------------------------------------------------------------- #
import base64 as _b64  # noqa: E402
import os as _os  # noqa: E402
from datetime import date as _d  # noqa: E402

from app.db.models import (  # noqa: E402
    InstagramQueueItem as _IGItem,
    NewsItem as _News,
)
from app.services.instagram import (  # noqa: E402
    graph_api as _ig_graph,
    publisher as _ig_publisher,
    scheduling as _ig_scheduling,
)


class AdminIGItem(BaseModel):
    id: int
    day: str
    slot: int
    position: int = 0
    status: str
    content_type: str = "news"
    media_type: str = "IMAGE"
    media_count: int = 1
    publish_on: str | None = None
    publish_at: datetime | None = None
    title: str
    category: str | None = None
    summary: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    image_url: str | None = None
    ig_media_id: str | None = None
    error: str | None = None
    is_blog: bool = False
    is_prepared: bool = False
    has_caption: bool = False
    created_at: datetime
    published_at: datetime | None = None


class AdminIGMedia(BaseModel):
    """Una pieza de media del post, para la previsualización del panel.

    Sin bytes: se sirven por `/media/{position}`. Diez diapositivas en base64
    serían ~5 MB por petición de detalle, y un vídeo mucho más.
    """
    position: int
    kind: str = "image"
    role: str | None = None
    url: str | None = None
    duration_s: float | None = None
    has_local: bool = False


class AdminIGItemDetail(AdminIGItem):
    caption: str | None = None
    # Imagen preparada, codificada en base64 para previsualizarla en el
    # panel sin tener que exponer el fichero local del contenedor.
    # Solo se rellena en posts de una pieza; el resto va por `media`.
    image_b64: str | None = None
    media: list[AdminIGMedia] = []


class AdminIGNewsCandidate(BaseModel):
    id: int
    title: str
    category: str | None = None
    source_medium: str | None = None
    source_name: str
    url: str
    policy: str
    relevance_score: float
    published_at: datetime | None
    fetched_at: datetime


class AdminIGEnqueueIn(BaseModel):
    news_item_id: int | None = None
    blog_post_id: int | None = None


class AdminIGPublishIn(BaseModel):
    dry_run: bool = False


class AdminIGReorderIn(BaseModel):
    # IDs de los items publicables (pending/prepared) en el orden de
    # publicación deseado: el primero se publica antes.
    ids: list[int]


class AdminIGBulkIn(BaseModel):
    # IDs de propuestas evergreen para aprobar/descartar en bloque.
    ids: list[int]


class AdminIGBulkResult(BaseModel):
    ok: list[int] = []
    failed: list[dict] = []


class AdminIGUpdateIn(BaseModel):
    # Edición manual del contenido antes de publicar. Cualquier campo None se
    # deja como está.
    caption: str | None = None
    title: str | None = None
    summary: str | None = None
    # Programación exacta. Para DESprogramar (devolver el item al goteo) hay que
    # mandar `clear_publish_at: true`: un None aquí significa "no tocar".
    publish_at: datetime | None = None
    clear_publish_at: bool = False
    # Formato: IMAGE | CAROUSEL | REELS. Cambiarlo exige re-preparar.
    media_type: str | None = None


class AdminIGAccount(BaseModel):
    ok: bool
    message: str
    username: str | None = None


def _ig_item_to_model(it: _IGItem) -> AdminIGItem:
    return AdminIGItem(
        id=it.id,
        day=it.day.isoformat() if it.day else "",
        slot=it.slot,
        position=it.position,
        status=it.status,
        content_type=getattr(it, "content_type", None) or "news",
        media_type=getattr(it, "media_type", None) or "IMAGE",
        media_count=len(getattr(it, "media", []) or []) or 1,
        publish_on=it.publish_on.isoformat() if getattr(it, "publish_on", None) else None,
        publish_at=getattr(it, "publish_at", None),
        title=it.title,
        category=it.category,
        summary=it.summary,
        source_name=it.source_name,
        source_url=it.source_url,
        image_url=it.image_url,
        ig_media_id=it.ig_media_id,
        error=it.error,
        is_blog=it.blog_post_id is not None,
        is_prepared=bool(it.image_path),
        has_caption=bool(it.caption),
        created_at=it.created_at,
        published_at=it.published_at,
    )


@router.get("/instagram/queue", response_model=list[AdminIGItem])
def admin_ig_queue_list(
    status: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[AdminIGItem]:
    q = db.query(_IGItem)
    if status and status != "all":
        q = q.filter(_IGItem.status == status)
    rows = (
        q.order_by(_IGItem.day.desc(), _IGItem.slot, _IGItem.created_at.desc())
        .limit(min(limit, 500))
        .all()
    )
    return [_ig_item_to_model(it) for it in rows]


def _ig_detail_model(it: _IGItem) -> AdminIGItemDetail:
    """Modelo de detalle para el panel.

    La primera imagen sigue yendo en base64 por compatibilidad, pero SOLO si el
    post es de una pieza y no es vídeo: un carrusel de 10 serían ~5 MB por
    petición y un MP4 bastante más. El resto se sirve por `/media/{position}`.
    """
    base = _ig_item_to_model(it)
    piezas = sorted(getattr(it, "media", []) or [], key=lambda m: m.position)

    image_b64 = None
    solo_una_imagen = len(piezas) <= 1 and not any(m.kind == "video" for m in piezas)
    if solo_una_imagen and it.image_path and _os.path.exists(it.image_path):
        with open(it.image_path, "rb") as f:
            image_b64 = _b64.b64encode(f.read()).decode("ascii")

    return AdminIGItemDetail(
        **base.model_dump(),
        caption=it.caption,
        image_b64=image_b64,
        media=[
            AdminIGMedia(
                position=m.position, kind=m.kind, role=m.role, url=m.url,
                duration_s=m.duration_s,
                has_local=bool(m.local_path and _os.path.exists(m.local_path)),
            )
            for m in piezas
        ],
    )


@router.get("/instagram/queue/{item_id}/media/{position}")
def admin_ig_media_bytes(
    item_id: int,
    position: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Sirve una pieza de media (imagen o vídeo) para previsualizarla.

    Prioriza el fichero local recién generado; si ya no está en `/tmp` (que es
    efímero) pero se subió a Cloudinary, redirige allí.
    """
    from fastapi.responses import FileResponse, RedirectResponse

    it = db.get(_IGItem, item_id)
    if it is None:
        raise HTTPException(status_code=404, detail="item not found")
    pieza = next(
        (m for m in (getattr(it, "media", []) or []) if m.position == position), None
    )
    if pieza is None:
        raise HTTPException(status_code=404, detail="media not found")

    if pieza.local_path and _os.path.exists(pieza.local_path):
        tipo = "video/mp4" if pieza.kind == "video" else "image/jpeg"
        return FileResponse(pieza.local_path, media_type=tipo)
    if pieza.url:
        return RedirectResponse(pieza.url)
    raise HTTPException(status_code=404, detail="media sin fichero ni URL")


@router.get("/instagram/queue/{item_id}", response_model=AdminIGItemDetail)
def admin_ig_queue_detail(
    item_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminIGItemDetail:
    it = db.get(_IGItem, item_id)
    if it is None:
        raise HTTPException(status_code=404, detail="item not found")
    return _ig_detail_model(it)


@router.patch("/instagram/queue/{item_id}", response_model=AdminIGItemDetail)
def admin_ig_update(
    item_id: int,
    payload: AdminIGUpdateIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminIGItemDetail:
    """Edita a mano el contenido de un item de la cola (caption, título,
    resumen) y su programación, antes de publicarlo. No se puede editar uno ya
    publicado."""
    it = db.get(_IGItem, item_id)
    if it is None:
        raise HTTPException(status_code=404, detail="item not found")
    if it.status == "published":
        raise HTTPException(status_code=409, detail="ya está publicado")
    if payload.caption is not None:
        it.caption = payload.caption
    if payload.title is not None:
        it.title = payload.title[:300]
    if payload.summary is not None:
        it.summary = payload.summary
    if payload.media_type is not None:
        if payload.media_type not in ("IMAGE", "CAROUSEL", "REELS", "CLIP", "PRODUCT"):
            raise HTTPException(status_code=400, detail="formato no válido")
        if payload.media_type != it.media_type:
            # Cambiar de formato invalida el material: hay que rehacerlo. Sin
            # esto el post se quedaba con las piezas del formato anterior y la
            # etiqueta mentía — un «carrusel · 1», que no existe. Es lo mismo
            # que ya hacía `scheduling.repartir_formatos`, y aquí faltaba.
            it.media.clear()
            it.image_path = None
            it.status = "pending"
        it.media_type = payload.media_type
        # Elegido por una persona: el repartidor automático ya no lo toca.
        it.media_locked = True
    if payload.clear_publish_at:
        it.publish_at = None          # vuelve al goteo normal
    elif payload.publish_at is not None:
        programado = payload.publish_at
        # Sin zona horaria se interpreta como UTC, que es como corre el cron.
        if programado.tzinfo is None:
            programado = programado.replace(tzinfo=timezone.utc)
        it.publish_at = programado
    db.commit()
    db.refresh(it)
    return _ig_detail_model(it)


@router.get("/instagram/news", response_model=list[AdminIGNewsCandidate])
def admin_ig_news_candidates(
    limit: int = 50,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[AdminIGNewsCandidate]:
    """Noticias recientes aptas para encolar a mano en Instagram."""
    rows = (
        db.query(_News)
        .order_by(_News.relevance_score.desc(), _News.fetched_at.desc())
        .limit(min(limit, 200))
        .all()
    )
    return [
        AdminIGNewsCandidate(
            id=n.id,
            title=n.title,
            category=n.category,
            source_medium=n.source_medium,
            source_name=n.source_name,
            url=n.url,
            policy=n.policy,
            relevance_score=n.relevance_score or 0.0,
            published_at=n.published_at,
            fetched_at=n.fetched_at,
        )
        for n in rows
    ]


@router.post("/instagram/enqueue", response_model=AdminIGItem)
def admin_ig_enqueue(
    payload: AdminIGEnqueueIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminIGItem:
    """Encola un item manualmente (noticia o artículo del blog)."""
    if payload.news_item_id is None and payload.blog_post_id is None:
        raise HTTPException(status_code=400, detail="indica news_item_id o blog_post_id")

    today = _d.today()
    if payload.news_item_id is not None:
        news = db.get(_News, payload.news_item_id)
        if news is None:
            raise HTTPException(status_code=404, detail="noticia no encontrada")
        existing = (
            db.query(_IGItem)
            .filter(_IGItem.news_item_id == news.id)
            .first()
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail="esa noticia ya está en cola")
        max_slot = (
            db.query(func.coalesce(func.max(_IGItem.slot), 0))
            .filter(_IGItem.day == today, _IGItem.slot >= 1)
            .scalar()
        )
        it = _IGItem(
            news_item_id=news.id,
            day=today,
            slot=int(max_slot) + 1,
            title=news.title[:300],
            category=news.category or "Actualidad",
            summary=news.summary,
            source_name=news.source_medium or news.source_name,
            source_url=news.url,
            status="pending",
        )
    else:
        from app.db.models import Post as _Post
        post = db.get(_Post, payload.blog_post_id)
        if post is None:
            raise HTTPException(status_code=404, detail="post no encontrado")
        existing = (
            db.query(_IGItem)
            .filter(_IGItem.blog_post_id == post.id)
            .first()
        )
        if existing is not None:
            raise HTTPException(status_code=409, detail="ese artículo ya está en cola")
        from app.services.instagram import config as _ig_config
        it = _IGItem(
            blog_post_id=post.id,
            day=today,
            slot=0,  # blog tiene prioridad
            title=post.title[:300],
            category="Blog",
            summary=post.excerpt,
            source_name="Entre Interiores · Blog",
            source_url=f"{_ig_config.SITE_URL}/blog/{post.slug}",
            status="pending",
        )

    # Va al final de la cola de publicación; el admin puede subirlo a mano.
    max_pos = db.query(func.coalesce(func.max(_IGItem.position), -1)).scalar()
    it.position = int(max_pos) + 1

    db.add(it)
    db.commit()
    db.refresh(it)
    return _ig_item_to_model(it)


@router.post("/instagram/queue/reorder", response_model=list[AdminIGItem])
def admin_ig_reorder(
    payload: AdminIGReorderIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[AdminIGItem]:
    """Reordena el orden de publicación de la cola.

    Recibe los IDs de los items publicables (pending/prepared) en el orden
    deseado y reasigna `position` = índice. No toca items ya publicados o
    descartados (su orden ya no importa).
    """
    if not payload.ids:
        raise HTTPException(status_code=400, detail="lista de ids vacía")
    items = {
        it.id: it
        for it in db.query(_IGItem).filter(_IGItem.id.in_(payload.ids)).all()
    }
    faltan = [i for i in payload.ids if i not in items]
    if faltan:
        raise HTTPException(status_code=404, detail=f"ids no encontrados: {faltan}")
    for pos, item_id in enumerate(payload.ids):
        items[item_id].position = pos
    db.commit()
    rows = (
        db.query(_IGItem)
        .filter(_IGItem.id.in_(payload.ids))
        .order_by(_IGItem.position)
        .all()
    )
    return [_ig_item_to_model(it) for it in rows]


@router.post("/instagram/queue/{item_id}/prepare", response_model=AdminIGItem)
def admin_ig_prepare(
    item_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminIGItem:
    """Genera (o regenera) imagen + caption para un item."""
    it = db.get(_IGItem, item_id)
    if it is None:
        raise HTTPException(status_code=404, detail="item not found")
    if it.status == "published":
        raise HTTPException(status_code=409, detail="ya está publicado")
    try:
        _ig_publisher.prepare(db, it)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"prepare falló: {exc}") from exc
    return _ig_item_to_model(it)


@router.post("/instagram/queue/{item_id}/publish", response_model=AdminIGItem)
def admin_ig_publish(
    item_id: int,
    payload: AdminIGPublishIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminIGItem:
    """Publica un item (o lo deja preparado si dry_run)."""
    it = db.get(_IGItem, item_id)
    if it is None:
        raise HTTPException(status_code=404, detail="item not found")
    if it.status == "published":
        raise HTTPException(status_code=409, detail="ya está publicado")
    _ig_publisher.publish(db, it, dry_run=payload.dry_run)
    return _ig_item_to_model(it)


@router.post("/instagram/queue/{item_id}/discard", response_model=AdminIGItem)
def admin_ig_discard(
    item_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminIGItem:
    it = db.get(_IGItem, item_id)
    if it is None:
        raise HTTPException(status_code=404, detail="item not found")
    if it.status == "published":
        raise HTTPException(status_code=409, detail="ya está publicado")
    it.status = "discarded"
    db.commit()
    db.refresh(it)
    return _ig_item_to_model(it)


@router.post("/instagram/queue/interleave", response_model=list[AdminIGItem])
def admin_ig_interleave(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[AdminIGItem]:
    """Reordena la cola publicable intercalando los tipos de contenido
    (round-robin por `content_type`), para que el goteo no saque varias del
    mismo tipo seguidas. NO toca el contenido con fecha fija (`publish_on`):
    ese se publica su día, no gotea."""
    items = (
        db.query(_IGItem)
        .filter(
            _IGItem.status.in_(("pending", "prepared")),
            _IGItem.publish_on.is_(None),
        )
        .order_by(_IGItem.position, _IGItem.created_at)
        .all()
    )
    # Agrupa por tipo conservando el orden interno actual.
    grupos: dict[str, list] = {}
    for it in items:
        grupos.setdefault(it.content_type or "news", []).append(it)
    # Round-robin: una de cada tipo por ronda (orden de tipo estable).
    orden_tipos = list(grupos.keys())
    interleaved: list = []
    i = 0
    while any(grupos[t] for t in orden_tipos):
        t = orden_tipos[i % len(orden_tipos)]
        if grupos[t]:
            interleaved.append(grupos[t].pop(0))
        i += 1
    for pos, it in enumerate(interleaved):
        it.position = pos
    db.commit()
    return [_ig_item_to_model(it) for it in interleaved]


class AdminIGAutoScheduleIn(BaseModel):
    weeks: int = 4          # ventana: próximas N semanas
    dry_run: bool = False   # calcular y devolver el reparto sin escribirlo


class AdminIGAutoScheduleResult(BaseModel):
    scheduled: list[dict] = []   # [{id, title, when}]
    skipped: list[dict] = []     # [{id, title, reason}]
    weekly_cap: int = 0
    slots: list[str] = []


@router.post(
    "/instagram/queue/auto-schedule", response_model=AdminIGAutoScheduleResult
)
def admin_ig_auto_schedule(
    payload: AdminIGAutoScheduleIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminIGAutoScheduleResult:
    """Reparte los posts aprobados y sin fecha por las próximas `weeks` semanas.

    Intercala tipos de contenido y respeta el techo semanal que impone el
    cuentagotas, así que no puede saltarse la cadencia acordada. Con
    `dry_run=true` devuelve el reparto propuesto sin tocar nada.
    """
    asignaciones, descartes = _ig_scheduling.plan(db, weeks=payload.weeks)
    if not payload.dry_run:
        _ig_scheduling.apply_plan(db, asignaciones)
    return AdminIGAutoScheduleResult(
        scheduled=[
            {"id": it.id, "title": it.title[:80], "when": cuando.isoformat()}
            for it, cuando in asignaciones
        ],
        skipped=descartes,
        weekly_cap=_ig_scheduling.cap_semanal(),
        slots=[h.strftime("%H:%M") for h in _ig_scheduling.slots_diarios()],
    )


# --------------------------------------------------------------------------- #
# Clips de vídeo de terceros
# --------------------------------------------------------------------------- #
class AdminClipIn(BaseModel):
    url: str
    start_s: float = 0.0
    end_s: float
    subtitle: str | None = None


class AdminClipOut(BaseModel):
    id: int
    video_id: str
    url: str
    video_title: str | None = None
    channel_title: str | None = None
    channel_url: str | None = None
    start_s: float
    end_s: float
    subtitle: str | None = None
    status: str
    url_cdn: str | None = None
    duration_s: float | None = None
    error: str | None = None
    requested_by: str | None = None
    ig_media_id: str | None = None
    queue_item_id: int | None = None
    retired_at: datetime | None = None
    retired_reason: str | None = None
    created_at: datetime


class AdminClipRetireIn(BaseModel):
    reason: str


def _clip_model(c) -> AdminClipOut:
    return AdminClipOut(
        id=c.id, video_id=c.video_id, url=c.url, video_title=c.video_title,
        channel_title=c.channel_title, channel_url=c.channel_url,
        start_s=c.start_s, end_s=c.end_s, subtitle=c.subtitle, status=c.status,
        url_cdn=c.url_cdn, duration_s=c.duration_s, error=c.error,
        requested_by=c.requested_by, ig_media_id=c.ig_media_id,
        queue_item_id=c.queue_item_id,
        retired_at=c.retired_at, retired_reason=c.retired_reason,
        created_at=c.created_at,
    )


@router.get("/instagram/clips", response_model=list[AdminClipOut])
def admin_clips_list(
    limit: int = 100,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[AdminClipOut]:
    """Todos los clips con su procedencia. Es el registro que se consulta si
    llega una reclamación."""
    from app.db.models import VideoClip

    rows = (
        db.query(VideoClip)
        .order_by(VideoClip.created_at.desc())
        .limit(min(limit, 500))
        .all()
    )
    return [_clip_model(c) for c in rows]


@router.post("/instagram/clips", response_model=AdminClipOut)
def admin_clips_create(
    payload: AdminClipIn,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
) -> AdminClipOut:
    """Pide un clip de YouTube. La descarga la hace el daemon de la Mac: la IP
    del servidor está bloqueada por YouTube."""
    from app.services.instagram import video_clips as _vc

    try:
        clip = _vc.solicitar(
            db, url=payload.url, start_s=payload.start_s, end_s=payload.end_s,
            subtitle=payload.subtitle, requested_by=admin.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _clip_model(clip)


@router.post("/instagram/clips/{clip_id}/retire", response_model=AdminClipOut)
def admin_clips_retire(
    clip_id: int,
    payload: AdminClipRetireIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminClipOut:
    """Retira un clip: borra el post de Instagram y el fichero de Cloudinary.

    Es la válvula que hace asumible publicar sin pedir permiso previo — permite
    responder a una reclamación en minutos.
    """
    from app.db.models import VideoClip
    from app.services.instagram import video_clips as _vc

    clip = db.get(VideoClip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="clip no encontrado")
    ok, msg = _vc.retire(db, clip, payload.reason)
    db.refresh(clip)
    if not ok:
        logger.warning("[clip] retirada parcial de %s: %s", clip_id, msg)
    return _clip_model(clip)


class AdminClipAssignIn(BaseModel):
    queue_item_id: int | None = None   # None = desasignar


@router.post("/instagram/clips/{clip_id}/assign", response_model=AdminClipOut)
def admin_clips_assign(
    clip_id: int,
    payload: AdminClipAssignIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminClipOut:
    """Reasigna el clip a OTRA publicación de la cola (o lo desasigna).

    Ya no es el camino normal: al pedir un clip se crea su propia publicación,
    con el clip como tema. Esto queda como válvula para moverlo de sitio, y el
    post destino pasa a `pending` para que haya que re-prepararlo.
    """
    from app.db.models import VideoClip

    clip = db.get(VideoClip, clip_id)
    if clip is None:
        raise HTTPException(status_code=404, detail="clip no encontrado")
    if clip.status == "retired":
        raise HTTPException(status_code=409, detail="el clip está retirado")

    if payload.queue_item_id is None:
        clip.queue_item_id = None
        db.commit()
        db.refresh(clip)
        return _clip_model(clip)

    item = db.get(_IGItem, payload.queue_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="publicación no encontrada")
    if item.status == "published":
        raise HTTPException(status_code=409, detail="esa publicación ya salió")

    clip.queue_item_id = item.id
    # CLIP, no REELS: un reel es vídeo PROPIO y va mudo (la música tiene
    # derechos); un clip es de otro canal y lleva su sonido y su atribución
    # quemada. Poner REELS aquí obligaba a que `prepare` lo corrigiera después.
    item.media_type = "CLIP"
    item.media_locked = True      # lo ha decidido una persona
    item.status = "pending"
    item.image_path = None
    item.media.clear()
    db.commit()
    db.refresh(clip)
    return _clip_model(clip)


@router.post("/instagram/queue/generate-product", response_model=AdminIGBulkResult)
def admin_ig_generate_product(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminIGBulkResult:
    """Crea posts PROPIOS que enseñan la web y los encola.

    Cada post es una consulta real («¿Qué es la libertad para Robe?»), no la
    funcionalidad en abstracto, y la pieza se compone preguntando a la API DE
    VERDAD. Son posts independientes: ya no se le cuelga el formato encima a una
    noticia que iba de otra cosa.

    Cantidad acotada por la cuota semanal (≈10% del feed): esto es el gancho de
    registro, no un folleto.
    """
    from app.services.instagram import evergreen as _ev
    from app.services.instagram import scheduling as _sched

    result = AdminIGBulkResult()
    usados = _ev.used_content_keys(db)
    cupo = _sched.cupo_libre(db, "product")
    if cupo <= 0:
        result.failed.append({
            "id": 0,
            "error": "ya hay posts de «la web» suficientes para las próximas "
                     "semanas (cuota ~10% del feed)",
        })
        return result

    candidatos = _ev.gen_product(db, count=cupo, used=usados)
    if not candidatos:
        result.failed.append({
            "id": 0,
            "error": "sin consultas nuevas con las que enseñar la web "
                     "(ya han salido todas las del registro y el corpus)",
        })
        return result

    pos = db.query(func.coalesce(func.max(_IGItem.position), -1)).scalar() or -1
    for i, cand in enumerate(candidatos, start=1):
        it = _IGItem(
            day=_date.today(), slot=2, position=pos + i,
            content_type=cand["content_type"], content_key=cand["content_key"],
            title=cand["title"][:300], category=cand.get("category"),
            summary=cand.get("summary"), source_name=cand.get("source_name"),
            # Sin esto se quedaban en IMAGE y `prepare` los mandaba a la rama
            # genérica en vez de a `_prepare_product`: salía arte IA cualquiera
            # en lugar de la pieza que enseña la funcionalidad. `media_locked`
            # los protege del repartidor de formatos.
            media_type="PRODUCT", media_locked=True,
            status="proposed",
        )
        db.add(it)
        db.commit()
        db.refresh(it)
        try:
            _ig_publisher.prepare(db, it)
            result.ok.append(it.id)
        except Exception as exc:  # noqa: BLE001
            it.status = "failed"
            it.error = f"prepare: {exc}"
            db.commit()
            result.failed.append({"id": it.id, "error": str(exc)[:200]})
    return result



class AdminIGShuffleIn(BaseModel):
    # Cambiar la semilla da otro reparto; con la misma, el resultado se repite.
    seed: int = 0
    # Por defecto solo toca los programados; con False, toda la cola activa.
    only_scheduled: bool = True


class AdminIGShuffleResult(BaseModel):
    changed: list[dict] = []   # [{id, title, antes, ahora}]
    mix: list[str] = []        # la mezcla objetivo desplegada


@router.post("/instagram/queue/shuffle-formats", response_model=AdminIGShuffleResult)
def admin_ig_shuffle_formats(
    payload: AdminIGShuffleIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminIGShuffleResult:
    """Reparte formatos variados (foto / carrusel / reel) entre los posts.

    Evita que el feed salga monótono. NO toca los que tienen el formato elegido
    a mano (`media_locked`). Los que cambian de formato vuelven a `pending` y hay
    que re-prepararlos, porque el material hay que regenerarlo.
    """
    cambios = _ig_scheduling.repartir_formatos(
        db, semilla=payload.seed, solo_programados=payload.only_scheduled
    )
    return AdminIGShuffleResult(
        changed=cambios, mix=_ig_scheduling.mezcla_formatos()
    )


class AdminIGBulkPrepareIn(BaseModel):
    # Sin ids, prepara TODO lo que esté pendiente y sin material.
    ids: list[int] | None = None
    limit: int = 20


@router.post("/instagram/queue/bulk-prepare", response_model=AdminIGBulkResult)
def admin_ig_bulk_prepare(
    payload: AdminIGBulkPrepareIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminIGBulkResult:
    """Genera el material de los posts que se quedaron sin él.

    Hace falta porque el repartidor de formatos deja en `pending` y sin
    material todo lo que cambia de formato (las diapositivas de un carrusel no
    valen para un reel). Sin esto habría que entrar post por post.

    `limit` acota el coste: generar un reel o un carrusel no es gratis.
    """
    q = db.query(_IGItem).filter(_IGItem.status.in_(("pending", "prepared")))
    if payload.ids:
        q = q.filter(_IGItem.id.in_(payload.ids))
    else:
        q = q.filter(_IGItem.caption.is_(None) | (_IGItem.image_path.is_(None)))
    items = q.order_by(_IGItem.position, _IGItem.id).limit(
        max(1, min(payload.limit, 50))
    ).all()

    result = AdminIGBulkResult()
    for it in items:
        try:
            _ig_publisher.prepare(db, it)
            result.ok.append(it.id)
        except Exception as exc:  # noqa: BLE001
            it.status = "failed"
            it.error = f"prepare: {exc}"
            db.commit()
            result.failed.append({"id": it.id, "error": str(exc)[:200]})
    return result


@router.post("/instagram/queue/bulk-approve", response_model=AdminIGBulkResult)
def admin_ig_bulk_approve(
    payload: AdminIGBulkIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminIGBulkResult:
    """Aprueba en bloque propuestas evergreen (`proposed`): las pasa a la cola de
    publicación y les genera imagen + caption (`prepare`). Si una falla al
    preparar, se marca `failed` y se reporta sin tumbar el resto."""
    if not payload.ids:
        raise HTTPException(status_code=400, detail="lista de ids vacía")
    result = AdminIGBulkResult()
    for item_id in payload.ids:
        it = db.get(_IGItem, item_id)
        if it is None:
            result.failed.append({"id": item_id, "error": "no encontrado"})
            continue
        if it.status != "proposed":
            result.failed.append({"id": item_id, "error": f"estado {it.status}"})
            continue
        it.status = "pending"
        db.commit()
        try:
            # Si ya venía preparado (lo hace `prepare_daily` para que la vista
            # previa del panel sea real), no se regenera: `prepare` cuesta una
            # llamada a OpenAI y perdería cualquier edición del caption.
            if not it.caption or not it.image_path:
                _ig_publisher.prepare(db, it)
            result.ok.append(item_id)
        except Exception as exc:  # noqa: BLE001
            it.status = "failed"
            it.error = f"prepare: {exc}"
            db.commit()
            result.failed.append({"id": item_id, "error": str(exc)})
    return result


@router.post("/instagram/queue/bulk-discard", response_model=AdminIGBulkResult)
def admin_ig_bulk_discard(
    payload: AdminIGBulkIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> AdminIGBulkResult:
    """Descarta en bloque propuestas. No se vuelven a proponer (su `content_key`
    queda registrado)."""
    if not payload.ids:
        raise HTTPException(status_code=400, detail="lista de ids vacía")
    result = AdminIGBulkResult()
    for item_id in payload.ids:
        it = db.get(_IGItem, item_id)
        if it is None:
            result.failed.append({"id": item_id, "error": "no encontrado"})
            continue
        if it.status == "published":
            result.failed.append({"id": item_id, "error": "ya publicado"})
            continue
        it.status = "discarded"
        db.commit()
        result.ok.append(item_id)
    return result


@router.get("/instagram/account", response_model=AdminIGAccount)
def admin_ig_account(
    _admin: User = Depends(get_current_admin),
) -> AdminIGAccount:
    """Verifica token + que la cuenta IG sea realmente alcanzable.

    No basta con que el token tenga scope: si el enlace IG↔Página se rompe,
    `token_is_valid()` sigue dando verde pero no se puede publicar. Aquí se
    hace una lectura real de la cuenta y se refleja el estado de verdad.
    """
    ok, msg, username = _ig_graph.connection_is_healthy()
    return AdminIGAccount(ok=ok, message=msg, username=username)


# --------------------------------------------------------------------------- #
# Knowledge graph: extraer cualquier subgrafo bajo demanda (p.ej. universo de X)
# --------------------------------------------------------------------------- #
@router.get("/graph/{entity_type}/{slug}")
def admin_graph(
    entity_type: str,
    slug: str,
    depth: int = 2,
    max_nodes: int = 60,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> dict:
    """Subgrafo del knowledge graph centrado en (entity_type, slug).

    Devuelve {center, nodes, edges}. Ej.: /admin/graph/person/inaki-milindris?depth=2
    para "el universo de Milindris".
    """
    from app.services import graph as graph_svc
    return graph_svc.subgraph(
        db, entity_type, slug,
        depth=max(1, min(depth, 4)),
        max_nodes=max(5, min(max_nodes, 200)),
    )
