"""Generación del borrador editorial de una propuesta.

Antes esta lógica vivía dentro de `scripts/blog/materialize_proposals.py` y solo
corría al publicar. Ahora se invoca **al aprobar** una propuesta: genera el
cuerpo (RAG), elige la foto, sanea y enlaza, y deja todo guardado en la propia
`ContentProposal` (body_md, excerpt, meta, hero, entities). Así "aprobadas"
contiene borradores ya revisables, y `materialize_proposals` solo copia el
borrador al `Post` y lo publica el día programado.

Idempotente por estado: si la propuesta ya tiene `body_md`, `generate_body`
no se vuelve a llamar (las noticias ya traen cuerpo del scraper); el
post-procesado (hero + saneado + enlazado) se aplica una vez al construir el
borrador.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select

from app.db.models import (
    Album,
    Artist,
    Concept,
    ContentProposal,
    Place,
    SeoContent,
    Song,
    Theme,
)
from app.services.content_generator import (
    generate_album_anniversary,
    generate_anniversary,
    generate_evergreen_topic,
    generate_seo_article,
    generate_song_spotlight,
)
from scripts.blog.context_builder import (
    album_context,
    artist_context,
    song_context,
    taxonomy_context,
)

logger = logging.getLogger(__name__)

ROBE = "Robe Iniesta"


def generate_body(db, p: ContentProposal) -> dict | None:
    """Genera el contenido editorial de una propuesta sin body, según kind.
    Devuelve dict con title/excerpt/body_md/meta_title/meta_description/entities
    o None si no se pudo."""
    today = date.today()

    if p.kind == "spotlight" and p.source_type == "song" and p.source_id:
        song = db.get(Song, p.source_id)
        if not song:
            return None
        album = db.get(Album, song.album_id)
        artist = db.get(Artist, album.artist_id) if album else None
        seo = db.execute(
            select(SeoContent).where(
                SeoContent.entity_type == "song", SeoContent.entity_id == song.id
            )
        ).scalar_one_or_none()
        try:
            ctx = song_context(db, song.id)
        except Exception:
            ctx = ""
        return generate_song_spotlight(
            song_title=song.title,
            album_title=album.title if album else "",
            artist_name=artist.name if artist else "",
            seo_excerpt=(seo.body_md if seo else None),
            context=ctx,
            today=today,
        )

    if p.kind == "album-anniversary" and p.source_type == "album" and p.source_id:
        album = db.get(Album, p.source_id)
        if not album:
            return None
        artist = db.get(Artist, album.artist_id)
        years = today.year - (
            album.release_date.year if album.release_date else today.year
        )
        track_titles = [
            t for (t,) in db.execute(
                select(Song.title).where(Song.album_id == album.id)
                .order_by(Song.track_number.nulls_last())
            ).all()
        ]
        try:
            ctx = album_context(db, album.id)
        except Exception:
            ctx = ""
        return generate_album_anniversary(
            album_title=album.title,
            artist_name=artist.name if artist else "",
            years_since=max(years, 1),
            release_year=album.release_date.year if album.release_date else album.year,
            track_titles=track_titles,
            context=ctx,
            today=today,
        )

    if p.kind == "anniversary":
        kind = "death" if p.source_type == "robe-death" else "birth"
        if kind == "death":
            years = today.year - 2025
        else:
            years = today.year - 1962
        try:
            robe = db.execute(
                select(Artist).where(Artist.slug == "robe")
            ).scalar_one_or_none()
            ctx = artist_context(db, robe.id) if robe else ""
        except Exception:
            ctx = ""
        return generate_anniversary(
            kind, person_name=ROBE, years_since=max(years, 1),
            context=ctx, today=today,
        )

    if p.kind == "evergreen":
        if p.source_type == "seo":
            return generate_seo_article(
                title=p.title,
                angle=p.angle,
                keywords=p.keywords or [],
                today=today,
            )
        model = {"theme": Theme, "place": Place, "concept": Concept}.get(
            p.source_type or ""
        )
        if model and p.source_id:
            tax = db.get(model, p.source_id)
            if tax:
                try:
                    song_ids = [s.id for s in tax.songs]
                    seo_tax = db.execute(
                        select(SeoContent).where(
                            SeoContent.entity_type == p.source_type,
                            SeoContent.entity_id == tax.id,
                        )
                    ).scalar_one_or_none()
                    ctx = taxonomy_context(
                        db, song_ids, seo_tax.body_md if seo_tax else None
                    )
                except Exception:
                    ctx = ""
                return generate_evergreen_topic(
                    taxonomy_kind=p.source_type,
                    taxonomy_name=tax.name,
                    taxonomy_description=tax.description,
                    song_titles=[s.title for s in tax.songs],
                    context=ctx,
                    today=today,
                )
        return None

    return None


def _post_process(db, body_md: str, entities: list) -> tuple[str, dict | None]:
    """Aplica hero (foto del sujeto) + saneado anti-IA + jerarquía de headings
    + enlazado interno automático. Devuelve (body_md, hero|None)."""
    from app.services.entity_resolver import (
        autolink_corpus,
        build_corpus_index,
        load_link_stats,
    )
    from app.services.hero_image import pick_hero_image
    from app.services.text_sanitizer import normalize_headings, strip_ai_tells

    hero = pick_hero_image(db, entities or [])
    body_md = strip_ai_tells(body_md) or body_md
    body_md = normalize_headings(body_md) or body_md
    body_md = autolink_corpus(
        body_md, build_corpus_index(db), max_links=4, link_stats=load_link_stats()
    )
    return body_md, hero


def generate_proposal_draft(db, p: ContentProposal) -> bool:
    """Construye el borrador completo de la propuesta y lo guarda en ella
    (body_md + excerpt + meta + hero + entities). Devuelve True si quedó listo.

    Pensado para invocarse al aprobar (en background) y como red de seguridad
    desde el cron `generate_approved_drafts` y desde `materialize_proposals`."""
    # 1. Cuerpo: el que ya trae (news) o generado por kind.
    if not p.body_md:
        payload = generate_body(db, p)
        if payload is None:
            logger.error("draft: no se pudo generar body para propuesta %s", p.id)
            return False
        p.title = (payload.get("title") or p.title)[:240]
        p.excerpt = payload.get("excerpt")
        p.body_md = payload["body_md"]
        p.meta_title = (payload.get("meta_title") or None)
        p.meta_description = (payload.get("meta_description") or None)
        p.entities = payload.get("entities") or []

    # 2. Post-procesado (hero + saneado + enlazado).
    body_md, hero = _post_process(db, p.body_md, p.entities or [])
    p.body_md = body_md
    if hero:
        p.hero_image_url = hero["url"]
        p.hero_image_attribution = hero["attribution"]
        p.hero_image_license = hero["license"]
        p.hero_image_source_url = hero["source"]
    if p.meta_title:
        p.meta_title = p.meta_title[:60]
    if p.meta_description:
        p.meta_description = p.meta_description[:155]

    db.commit()
    db.refresh(p)
    logger.info("draft listo para propuesta %s (%s)", p.id, p.kind)
    return True
