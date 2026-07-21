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
import os
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


def _deep_body(
    db, *, entity_type: str, entity, framing: str, coverage: str = "",
    extra_material: str = "", tier: str = "standard", serp_guidance: str = "",
) -> dict | None:
    """Genera un cuerpo con el MOTOR PROFUNDO (mismo que las páginas de entidad y
    las noticias): dossier RAG del corpus + outline adaptativo + sección a sección
    con anti-redundancia (`prior`) + verificación factual + pulido. Devuelve el
    dict editorial o None si no hay material para algo digno (lo decide el rigor
    aguas abajo). Sustituye al one-shot genérico que producía relleno.

    `extra_material`: material adicional REAL (p.ej. investigación web dirigida) que
    se suma al dossier del corpus. La verificación por sección sigue actuando: solo
    sobrevive lo que el material (corpus + extra) respalde (anti-invención)."""
    try:
        from openai import OpenAI

        from app.services.deep_research import gather_entity_dossier
        from app.services.news_research import _news_meta
        from app.services.text_sanitizer import strip_ai_tells
        from scripts.seo.generate_deep import (
            _coverage_hint, _outline, _polish, _verify_section, _write_section,
        )

        dossier = gather_entity_dossier(db, entity_type, entity)
        material = dossier.material or ""
        if extra_material.strip():
            material = f"{material}\n\nINVESTIGACIÓN WEB (material real adicional):\n{extra_material}"
        subject = dossier.subject
        cov = coverage or _coverage_hint(entity_type)
        hard = f"{framing}\nDATOS DUROS (úsalos, son verídicos):\n{dossier.hard_facts}"
        if serp_guidance.strip():
            hard += f"\n\n{serp_guidance.strip()}"

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        outline = _outline(client, subject, "", hard, material, cov, tier=tier)
        if not outline:
            return None
        headings = [s["heading"] for s in outline]
        parts: list[str] = []
        prior = ""
        for s in outline:
            sec = _write_section(client, subject, s, headings, hard, material, "",
                                 prior=prior, coverage=cov, tier=tier)
            sec = _verify_section(client, sec, material)
            if sec.strip():
                parts.append(sec.strip())
                prior = "\n\n".join(parts)
        body = "\n\n".join(parts)
        if len(body.strip()) < 300:
            return None
        body = _polish(client, subject, body) or body
        body = strip_ai_tells(body) or body
        meta = _news_meta(subject, body)
        return {
            "title": (meta.get("title") or subject)[:240],
            "excerpt": meta.get("excerpt") or "",
            "body_md": body,
            "meta_title": meta.get("meta_title") or "",
            "meta_description": meta.get("meta_description") or "",
            "entities": [],
        }
    except Exception as exc:  # noqa: BLE001 — degradar al generador clásico
        logger.warning("[draft] motor profundo falló (%s): %s", entity_type, exc)
        return None


def generate_body(db, p: ContentProposal) -> dict | None:
    """Genera el contenido editorial de una propuesta sin body, según kind.
    Devuelve dict con title/excerpt/body_md/meta_title/meta_description/entities
    o None si no se pudo. Los tipos anclados a una entidad real (canción, disco,
    Robe, taxonomía) usan el MOTOR PROFUNDO; si falla, caen al generador clásico.

    El `tier` de engagement (premium/flagship) sube la extensión/profundidad y, para
    esos temas, trae un brief de competencia SERP como guía de cobertura a superar."""
    today = date.today()
    _tier = getattr(p, "quality_tier", None) or "standard"
    _serp = ""
    if _tier in ("premium", "flagship", "cornerstone"):
        try:
            from app.services.serp_brief import build_brief
            _serp = build_brief(p.target_keyword or p.title or "")
        except Exception as exc:  # noqa: BLE001 — el brief es opcional
            logger.warning("draft: brief SERP falló: %s", exc)

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
        deep = _deep_body(
            db, entity_type="song", entity=song,
            framing=(
                f"Análisis a fondo de la canción «{song.title}»"
                + (f" del disco «{album.title}»" if album else "")
                + ". CITA versos textuales concretos entre comillas (copiados LITERAL "
                "de la letra real que tienes en el material [LETRA]; nunca inventes un "
                "verso), explica su significado, la música y su contexto. Nada genérico."
            ),
            tier=_tier, serp_guidance=_serp,
        )
        if deep:
            return deep
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
        rel_year = album.release_date.year if album.release_date else album.year
        deep = _deep_body(
            db, entity_type="album", entity=album,
            framing=(
                f"{max(years,1)} años del disco «{album.title}» (salió en {rel_year}). "
                "Cuenta el CONTEXTO y la grabación, el sello, las CANCIONES CLAVE "
                f"(nómbralas: {', '.join(track_titles[:12])}), el sonido y su lugar en "
                "la trayectoria. Datos concretos y citas si las hay; nada de loas vacías."
            ),
            tier=_tier, serp_guidance=_serp,
        )
        if deep:
            return deep
        try:
            ctx = album_context(db, album.id)
        except Exception:
            ctx = ""
        return generate_album_anniversary(
            album_title=album.title,
            artist_name=artist.name if artist else "",
            years_since=max(years, 1),
            release_year=rel_year,
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
        robe = db.execute(
            select(Artist).where(Artist.slug == "robe")
        ).scalar_one_or_none()
        label = "su muerte (diciembre de 2025)" if kind == "death" else "su nacimiento"
        if robe:
            deep = _deep_body(
                db, entity_type="artist", entity=robe,
                framing=(
                    f"Efeméride: {max(years,1)} años de {label} de Robe. Repasa hechos "
                    "biográficos y de su obra CONCRETOS y datados (discos, canciones, "
                    "momentos), citando lo verídico. Nada de loas genéricas."
                ),
                tier=_tier, serp_guidance=_serp,
            )
            if deep:
                return deep
        try:
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
                deep = _deep_body(
                    db, entity_type=p.source_type, entity=tax,
                    framing=(
                        f"Tema de fondo: «{tax.name}» en la obra de Robe/Extremoduro. "
                        "CITA versos textuales concretos donde aparece (copiados LITERAL "
                        "del material [LETRA]; nunca inventes un verso ni lo atribuyas a "
                        "una canción sin tener su letra) e ilústralo con canciones y "
                        "hechos reales. Nada de divagación genérica."
                    ),
                    tier=_tier, serp_guidance=_serp,
                )
                if deep:
                    return deep
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


def _post_process(db, body_md: str, entities: list, subject: str = "",
                  title: str = "") -> tuple[str, dict | None]:
    """Aplica hero ÚNICO (foto del sujeto sin repetir, o arte IA) + saneado anti-IA
    + jerarquía de headings + enlazado interno automático. Devuelve (body_md, hero|None)."""
    from app.services.blog_hero import build_unique_hero
    from app.services.entity_resolver import (
        autolink_corpus,
        build_corpus_index,
        load_link_stats,
    )
    from app.services.text_sanitizer import normalize_headings, strip_ai_tells

    hero = build_unique_hero(db, entities or [], subject, alt_label=title or subject)
    body_md = strip_ai_tells(body_md) or body_md
    body_md = normalize_headings(body_md) or body_md
    # Embebe vídeos referenciados como enlace markdown (URL desnuda → reproductor).
    from app.services.text_sanitizer import embed_youtube_links
    body_md = embed_youtube_links(body_md) or body_md
    body_md = autolink_corpus(
        body_md, build_corpus_index(db), max_links=4, link_stats=load_link_stats()
    )
    return body_md, hero


def _collect_videos(db, p: ContentProposal) -> None:
    """Consolida `p.videos` (lista). En premium/flagship añade vídeos REALES
    relacionados de la entidad (oficial/directo/entrevista) y los embebe en el
    cuerpo; cada uno emite su VideoObject en el schema. Best-effort."""
    videos: list[dict] = []
    seen: set[str] = set()
    if getattr(p, "video", None) and p.video.get("youtube_id"):
        videos.append(p.video)
        seen.add(p.video["youtube_id"])
    tier = getattr(p, "quality_tier", None) or "standard"
    if tier in ("premium", "flagship", "cornerstone"):
        try:
            from sqlalchemy import select

            from app.db.models import RelatedVideo, RelatedVideoEntity
            slugs = [e["slug_hint"] for e in (p.entities or []) if e.get("slug_hint")]
            if slugs:
                limit = {"cornerstone": 4, "flagship": 3}.get(tier, 2)
                rows = db.execute(
                    select(RelatedVideo)
                    .join(RelatedVideoEntity, RelatedVideoEntity.video_id == RelatedVideo.id)
                    .where(RelatedVideoEntity.entity_slug.in_(slugs))
                    .limit(10)
                ).scalars().all()
                added = 0
                for rv in rows:
                    if added >= limit or rv.youtube_id in seen:
                        continue
                    seen.add(rv.youtube_id)
                    added += 1
                    videos.append({
                        "youtube_id": rv.youtube_id, "title": rv.title,
                        "upload_date": rv.upload_date.isoformat() if rv.upload_date else None,
                        "channel": None,
                    })
                    p.body_md = (p.body_md or "").rstrip() + (
                        f"\n\nhttps://www.youtube.com/watch?v={rv.youtube_id}\n"
                    )
                if added:
                    logger.info("draft: %d vídeo(s) relacionado(s) en propuesta %s (%s)",
                                added, p.id, tier)
        except Exception as exc:  # noqa: BLE001 — multimedia es opcional
            logger.warning("draft: vídeos relacionados fallaron: %s", exc)
    if videos:
        p.videos = videos
        if not getattr(p, "video", None):
            p.video = videos[0]


def generate_proposal_draft(db, p: ContentProposal, *, persist: bool = True) -> bool:
    """Construye el borrador completo de la propuesta y lo guarda en ella
    (body_md + excerpt + meta + hero + entities). Devuelve True si quedó listo.

    Pensado para invocarse al aprobar (en background) y como red de seguridad
    desde el cron `generate_approved_drafts` y desde `materialize_proposals`.

    `persist`: si False, NO hace commit/refresh finales — para regenerar sobre una
    propuesta TRANSITORIA (no persistida) sin chocar con constraints ni dejar filas
    sueltas; el caller lee los campos en memoria (p.ej. regen_entity_post)."""
    # 0. Engagement: score + tier (modula extensión/profundidad/multimedia y activa
    #    el brief de competencia SERP en premium/flagship). Se calcula antes del
    #    cuerpo para que generate_body lo lea.
    if not p.quality_tier:
        try:
            from app.services.engagement import compute_for_proposal, content_tier
            score, tier = compute_for_proposal(db, p)
            p.engagement_score = score
            # Política: no-noticias con SUELO flagship; temáticas de alto engagement
            # → cornerstone. Las noticias mantienen su tier por actualidad.
            p.quality_tier = content_tier(p.kind, score, tier, p.source_type)
            logger.info("draft: propuesta %s → engagement %s (%s)",
                        p.id, p.engagement_score, p.quality_tier)
        except Exception as exc:  # noqa: BLE001
            logger.warning("draft: engagement falló: %s", exc)

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

    # 1b. Best-effort VÍDEO: si la propuesta no trae vídeo (kinds no-news), buscar
    #     uno claramente del tema y embeberlo (URL desnuda → reproductor + VideoObject).
    if not getattr(p, "video", None):
        try:
            from app.services.news_research import find_video
            subject = (p.target_keyword or p.title or "").strip()
            vid = find_video(subject, subject) if subject else None
            if vid:
                p.video = vid
                p.body_md = (p.body_md or "").rstrip() + (
                    f"\n\nhttps://www.youtube.com/watch?v={vid['youtube_id']}\n"
                )
                logger.info("draft: vídeo añadido a propuesta %s", p.id)
        except Exception as exc:  # noqa: BLE001 — el vídeo es opcional
            logger.warning("draft: búsqueda de vídeo falló: %s", exc)

    # 1c. Multimedia enriquecida: consolida la lista `videos` y, en premium/flagship,
    #     añade vídeos REALES relacionados de la entidad (oficial/directo/entrevista).
    _collect_videos(db, p)

    # 2. Post-procesado (hero ÚNICO + saneado + enlazado).
    subject = (p.target_keyword or p.title or "").strip()
    body_md, hero = _post_process(db, p.body_md, p.entities or [], subject, title=p.title)
    p.body_md = body_md
    if hero:
        p.hero_image_url = hero["url"]
        p.hero_image_alt = hero.get("alt")
        p.hero_image_attribution = hero["attribution"]
        p.hero_image_license = hero["license"]
        p.hero_image_source_url = hero["source"]
    if p.meta_title:
        p.meta_title = p.meta_title[:60]
    if p.meta_description:
        p.meta_description = p.meta_description[:155]

    if persist:
        db.commit()
        db.refresh(p)
        logger.info("draft listo para propuesta %s (%s)", p.id, p.kind)
    return True
