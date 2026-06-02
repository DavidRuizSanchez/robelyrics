"""Helpers comunes para los scripts de generación SEO.

Reglas legales/editoriales que TODOS los prompts deben respetar:
  - NO recitar más de 4 líneas seguidas de letra original (cita LPI 32).
  - NO copiar bloques textuales de fuentes; siempre parafrasear.
  - Tono editorial cercano y riguroso, tercera persona.
  - Spanish neutral (no jerga regional excesiva).
  - NO usar Genius como fuente directa (CC-BY-NC en privada, ya excluido por
    `for_seo_only=True` o `kind=genius_annotation` en el filtro).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import (
    Album,
    Artist,
    InterpretationSource,
    SeoContent,
    Song,
)
from scripts.research.common import log
from app.services.voice import build_system_prompt

MODEL = "gpt-4o"
# Voz única del sitio (1ª persona admiradora). Ver app/services/voice.py.
SYSTEM_PROMPT = build_system_prompt(family="seo")


def call_llm(client: OpenAI, user_prompt: str) -> dict[str, Any]:
    """Invoca GPT-4o con structured output JSON. Lanza ValueError si JSON inválido."""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.65,  # algo más de expresividad para que asome la voz de fan
        max_tokens=4000,
    )
    content = resp.choices[0].message.content
    if not content:
        raise ValueError("LLM devolvió contenido vacío")
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido del LLM: {e}; raw={content[:200]}") from e


def upsert_seo_content(
    db: Session,
    *,
    entity_type: str,
    entity_id: int,
    slug: str,
    body_md: str,
    meta_title: str | None,
    meta_description: str | None,
    schema_jsonld: dict | None,
    entities: list | None = None,
    force: bool = False,
) -> int:
    """Inserta o actualiza la fila correspondiente. Si ya existe y --force,
    sobrescribe body_md y reset reviewed_at + published. Si no force, falla."""
    # Saneado anti marcas de IA (em-dash, etc.) — red de seguridad por si el
    # LLM ignoró el SYSTEM_PROMPT.
    from app.services.text_sanitizer import normalize_headings, strip_ai_tells
    body_md = strip_ai_tells(body_md) or body_md
    body_md = normalize_headings(body_md) or body_md
    meta_title = strip_ai_tells(meta_title)
    meta_description = strip_ai_tells(meta_description)
    if not force:
        # Comprueba que no existe ya para evitar pisar revisión humana
        existing = (
            db.query(SeoContent)
            .filter(
                SeoContent.entity_type == entity_type,
                SeoContent.entity_id == entity_id,
            )
            .first()
        )
        if existing:
            log(
                f"  ya existe seo_content para {entity_type}/{slug} "
                f"(id={existing.id}, published={existing.published}); usa --force",
                "warn",
            )
            return existing.id

    ents = entities or []
    # Enlazado interno automático: enlaza hasta 4 menciones a entidades del
    # corpus (las más relevantes) a su página local. No enlaza la propia
    # página de este seo_content.
    if body_md:
        from app.services.entity_resolver import (
            autolink_corpus,
            build_corpus_index,
            load_link_stats,
        )
        body_md = autolink_corpus(
            body_md, build_corpus_index(db), max_links=4,
            exclude_slug=slug, link_stats=load_link_stats(),
        )

    stmt = (
        pg_insert(SeoContent)
        .values(
            entity_type=entity_type,
            entity_id=entity_id,
            slug=slug,
            body_md=body_md,
            meta_title=meta_title,
            meta_description=meta_description,
            schema_jsonld=schema_jsonld,
            entities=ents,
            generated_at=datetime.now(timezone.utc),
            generated_by=MODEL,
            reviewed_at=None,
            published=False,
        )
        .on_conflict_do_update(
            constraint="uq_seo_content_entity",
            set_={
                "slug": slug,
                "body_md": body_md,
                "meta_title": meta_title,
                "meta_description": meta_description,
                "schema_jsonld": schema_jsonld,
                "entities": ents,
                "generated_at": datetime.now(timezone.utc),
                "generated_by": MODEL,
                "reviewed_at": None,
                "published": False,
            },
        )
        .returning(SeoContent.id)
    )
    return int(db.execute(stmt).scalar_one())


def fetch_sources_for_song(db: Session, song_id: int) -> list[dict[str, Any]]:
    """Devuelve las fuentes (no-Genius) que mencionan a la canción, incluyendo
    las marcadas for_seo_only. Cada source en formato lite para el prompt."""
    rows = (
        db.execute(
            select(InterpretationSource)
            .where(InterpretationSource.referenced_song_ids.any(song_id))
            .where(InterpretationSource.kind != "genius_annotation")
        )
        .scalars()
        .all()
    )
    return [
        {
            "kind": r.kind,
            "title": r.title or "",
            "author": r.author or "",
            "for_seo_only": r.for_seo_only,
            "content": (r.content_clean or "")[:3000],  # truncamos por tokens
        }
        for r in rows
    ]


def fetch_sources_for_album(db: Session, album_id: int) -> list[dict[str, Any]]:
    """Fuentes que mencionan cualquier canción del álbum."""
    from sqlalchemy.dialects.postgresql import ARRAY
    from sqlalchemy import Integer as SAInteger, cast

    song_ids = [
        sid for (sid,) in db.execute(
            select(Song.id).where(Song.album_id == album_id)
        ).all()
    ]
    if not song_ids:
        return []
    # ARRAY overlap operator (&&) en Postgres
    rows = (
        db.execute(
            select(InterpretationSource)
            .where(
                InterpretationSource.referenced_song_ids.op("&&")(
                    cast(song_ids, ARRAY(SAInteger))
                )
            )
            .where(InterpretationSource.kind != "genius_annotation")
        )
        .scalars()
        .all()
    )
    # dedup por url para evitar repetidos cuando una fuente menciona varias canciones
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        if r.url in seen:
            continue
        seen.add(r.url)
        out.append({
            "kind": r.kind,
            "title": r.title or "",
            "author": r.author or "",
            "for_seo_only": r.for_seo_only,
            "content": (r.content_clean or "")[:3000],
        })
    return out


def fetch_sources_for_artist(db: Session, artist_id: int) -> list[dict[str, Any]]:
    """Top fuentes que mencionan al artista (todas sus canciones). Limitado a 20
    para no inundar el prompt — priorizamos `for_seo_only` (prensa profesional)."""
    song_ids = [
        sid for (sid,) in db.execute(
            select(Song.id)
            .join(Album, Song.album_id == Album.id)
            .where(Album.artist_id == artist_id)
        ).all()
    ]
    if not song_ids:
        return []
    from sqlalchemy.dialects.postgresql import ARRAY
    from sqlalchemy import Integer as SAInteger, cast
    rows = (
        db.execute(
            select(InterpretationSource)
            .where(
                InterpretationSource.referenced_song_ids.op("&&")(
                    cast(song_ids, ARRAY(SAInteger))
                )
            )
            .where(InterpretationSource.kind != "genius_annotation")
            .order_by(InterpretationSource.for_seo_only.desc(), InterpretationSource.id)
            .limit(20)
        )
        .scalars()
        .all()
    )
    return [
        {
            "kind": r.kind,
            "title": r.title or "",
            "author": r.author or "",
            "for_seo_only": r.for_seo_only,
            "content": (r.content_clean or "")[:2000],
        }
        for r in rows
    ]


def format_sources_block(sources: list[dict[str, Any]]) -> str:
    """Bloque legible para el prompt con las fuentes consultadas."""
    if not sources:
        return "(Sin fuentes externas adicionales — usa solo conocimiento general.)"
    blocks = []
    for i, s in enumerate(sources, 1):
        author = f" · {s['author']}" if s["author"] else ""
        head = f"FUENTE {i} [{s['kind']}{author}]: {s['title']}"
        blocks.append(f"{head}\n{s['content']}")
    return "\n\n---\n\n".join(blocks)


# --------------------------------------------------------------------------- #
# Conocimiento fan DESTILADO (SongInterpretation.payload). Mismo criterio de
# confianza que reranker.fetch_song_context (high/medium). Esto es lo que da
# PROFUNDIDAD y alma al contenido: el consenso de lo que los fans entienden de
# cada canción, ya destilado y con citación. Antes solo lo usaba la búsqueda
# privada; ahora también la generación de contenido público.
# --------------------------------------------------------------------------- #
def fetch_distilled_for_song(db: Session, song_id: int) -> dict[str, Any] | None:
    from app.db.models import SongInterpretation
    interp = (
        db.query(SongInterpretation)
        .filter(SongInterpretation.song_id == song_id)
        .first()
    )
    if not interp or interp.confidence not in ("high", "medium"):
        return None
    p = interp.payload or {}
    if not (p.get("fan_consensus") or p.get("themes") or p.get("key_metaphors")):
        return None
    return {
        "themes": p.get("themes") or [],
        "key_metaphors": p.get("key_metaphors") or [],
        "fan_consensus": p.get("fan_consensus") or "",
        "confidence": interp.confidence,
    }


def fetch_distilled_for_album(db: Session, album_id: int, *, limit: int = 14) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Song.id, Song.title).where(Song.album_id == album_id).order_by(Song.track_number)
    ).all()
    out: list[dict[str, Any]] = []
    for sid, title in rows:
        d = fetch_distilled_for_song(db, sid)
        if d:
            out.append({"song": title, **d})
        if len(out) >= limit:
            break
    return out


def fetch_distilled_for_artist(db: Session, artist_id: int, *, limit: int = 14) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Song.id, Song.title)
        .join(Album, Song.album_id == Album.id)
        .where(Album.artist_id == artist_id)
    ).all()
    out: list[dict[str, Any]] = []
    for sid, title in rows:
        d = fetch_distilled_for_song(db, sid)
        if d and d.get("fan_consensus"):
            out.append({"song": title, **d})
        if len(out) >= limit:
            break
    return out


def format_distilled_block(distilled: dict[str, Any] | list[dict[str, Any]] | None) -> str:
    """Bloque para el prompt con el consenso fan destilado.

    Acepta un dict (canción) o una lista de dicts (álbum/artista). Etiquetado
    para que el LLM lo use como FUNDAMENTO interpretativo, no como texto a
    recitar.
    """
    if not distilled:
        return ""
    items = [distilled] if isinstance(distilled, dict) else distilled
    if not items:
        return ""
    header = (
        "CONSENSO FAN DESTILADO (lo que la comunidad de fans entiende de estas "
        "canciones, ya destilado y consensuado). Úsalo como FUNDAMENTO de tu "
        "lectura interpretativa, intégralo y parafraséalo con tu voz; NO lo "
        "copies textual ni lo recites como si fuera la letra:"
    )
    blocks: list[str] = []
    for d in items:
        lines: list[str] = []
        if d.get("song"):
            lines.append(f"· {d['song']}")
        if d.get("themes"):
            lines.append("  Temas: " + ", ".join(str(t) for t in d["themes"][:6]))
        for m in (d.get("key_metaphors") or [])[:4]:
            if isinstance(m, dict) and m.get("phrase"):
                meaning = m.get("meaning") or ""
                lines.append(f"  Metáfora: «{m['phrase']}» -> {meaning}")
        if d.get("fan_consensus"):
            lines.append("  " + d["fan_consensus"])
        if lines:
            blocks.append("\n".join(lines))
    if not blocks:
        return ""
    return header + "\n" + "\n\n".join(blocks)
