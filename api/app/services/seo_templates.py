"""Resolución de plantillas SEO.

Cada `SeoContent` puede tener `meta_title`, `meta_description` y `h1` con un
valor concreto, o dejarlos a `None` para heredar la plantilla declarada en
`SeoTemplate` para su `entity_type` (+ `kind` si es álbum).

`resolve_all` devuelve los 3 campos ya resueltos; `render_with_context` aplica
la sustitución `{{var}}` → valor.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Album, Artist, SeoContent, SeoTemplate, Song

_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def render_with_context(template: str, ctx: dict[str, Any]) -> str:
    """Sustituye {{var}} por ctx[var]. Si var no está en ctx, deja literal."""
    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        if key in ctx and ctx[key] is not None:
            return str(ctx[key])
        return m.group(0)

    return _VAR_RE.sub(repl, template)


def _build_context(db: Session, row: SeoContent) -> dict[str, Any]:
    """Crea el contexto de variables disponibles para renderizar plantillas,
    cargando la entidad referenciada por (entity_type, entity_id)."""
    ctx: dict[str, Any] = {"slug": row.slug}

    if row.entity_type == "artist":
        a = db.get(Artist, row.entity_id)
        if a:
            ctx.update({
                "name": a.name,
                "artist": a.name,
                "title": a.name,
                "active_years": a.active_years or "",
            })
    elif row.entity_type == "album":
        al = db.get(Album, row.entity_id)
        if al:
            artist_name = al.artist.name if al.artist else ""
            ctx.update({
                "title": al.title,
                "artist": artist_name,
                "year": str(al.year) if al.year else "",
                "kind": al.kind or "",
            })
    elif row.entity_type == "song":
        s = db.get(Song, row.entity_id)
        if s:
            al = s.album
            artist_name = al.artist.name if al and al.artist else ""
            album_title = al.title if al else ""
            year = str(al.year) if al and al.year else ""
            kind = al.kind if al else ""
            ctx.update({
                "title": s.title,
                "album": album_title,
                "artist": artist_name,
                "year": year,
                "kind": kind,
            })

    return ctx


def _template_for(
    db: Session, entity_type: str, kind: str | None, field: str
) -> str | None:
    """Resuelve la plantilla más específica (kind exacto → kind NULL)."""
    if kind:
        t = db.execute(
            select(SeoTemplate).where(
                SeoTemplate.entity_type == entity_type,
                SeoTemplate.kind == kind,
                SeoTemplate.field == field,
            )
        ).scalar_one_or_none()
        if t:
            return t.template
    t = db.execute(
        select(SeoTemplate).where(
            SeoTemplate.entity_type == entity_type,
            SeoTemplate.kind.is_(None),
            SeoTemplate.field == field,
        )
    ).scalar_one_or_none()
    return t.template if t else None


def resolve_all(db: Session, row: SeoContent) -> dict[str, str | None]:
    """Devuelve {title, description, h1} resueltos. Si la fila trae override,
    lo usa. Si no, busca la plantilla más específica para (entity_type, kind)
    y la renderiza con el contexto de la entidad. Si no hay plantilla, None."""
    ctx = _build_context(db, row)
    kind = ctx.get("kind") or None

    def field_value(stored: str | None, field_name: str) -> str | None:
        if stored:
            return render_with_context(stored, ctx)
        tpl = _template_for(db, row.entity_type, kind, field_name)
        if not tpl:
            return None
        return render_with_context(tpl, ctx)

    return {
        "title": field_value(row.meta_title, "title"),
        "description": field_value(row.meta_description, "description"),
        "h1": field_value(row.h1, "h1"),
    }
