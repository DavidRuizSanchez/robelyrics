"""Materializa las propuestas programadas: cuando llega su `scheduled_for`,
crea el `Post` desde el borrador ya generado y lo publica.

Cron diario. Para cada `ContentProposal` con status='scheduled' y
`scheduled_for <= hoy`:
  1. Se asegura de que tenga borrador (`body_md`). Normalmente ya se generó al
     APROBARLA (`draft_generator.generate_proposal_draft`); si no, lo genera
     ahora como red de seguridad.
  2. Crea el `Post` copiando el borrador (cuerpo, foto, meta, entidades ya
     saneados y enlazados) y lo publica vía `auto_publish_post`.
  3. Marca la propuesta como `used` con `post_id`.

Uso:
    python -m scripts.blog.materialize_proposals
    python -m scripts.blog.materialize_proposals --dry-run
"""
from __future__ import annotations

import argparse
import logging
import re
import unicodedata
from datetime import date

from sqlalchemy import select

from app.db.models import ContentProposal, Post
from app.db.session import SessionLocal
from app.services.draft_generator import generate_proposal_draft
from app.services.editorial_review import review as editorial_review
from app.services.fact_check import check_body, correct_body
from app.services.focus_check import check_focus
from app.services.publishing import auto_publish_post, propose_for_review

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _notify_admin(subject: str, text: str) -> None:
    """Aviso best-effort al admin (p.ej. publicación caducada cancelada)."""
    import os

    admin_email = os.getenv("ADMIN_EMAIL")
    if not admin_email:
        logger.info("ADMIN: %s — %s", subject, text)
        return
    try:
        from app.services.email import send_email
        send_email(to=admin_email, subject=subject,
                   html=f"<pre style='font-family:monospace'>{text}</pre>", text=text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("aviso admin falló (%s); %s", exc, text)


def _build_chronicle(db, p: ContentProposal, today) -> dict | None:
    """Si el evento de `p` ya pasó, intenta reconstruir una CRÓNICA en pasado a
    partir de material web real. Devuelve el dict de `research_and_write` (modo
    crónica) o None si no hay material suficiente (→ se cancelará la publicación).

    Anti-invención: la generación en modo crónica pasa por la verificación
    factual contra el material; si el material no sostiene un relato, el cuerpo
    queda demasiado corto y se descarta (mejor cancelar que inventar lo ocurrido).
    """
    from app.services.news_research import research_and_write, web_research

    subject = (p.target_keyword or p.title or "").strip()
    year = p.event_date.year if p.event_date else today.year
    hits = web_research(f"crónica resumen qué pasó {subject} {year}", n=6)
    if len(hits) < 2:
        logger.info("  sin material de crónica para «%s»", subject)
        return None
    excerpt = "\n".join(f"- {h['title']}: {h['snippet']}" for h in hits)
    if p.body_md:
        excerpt += (
            "\n\nBORRADOR PREVIO (estaba en FUTURO; reconviértelo a crónica en "
            f"pasado, solo lo que el material confirme):\n{p.body_md[:2000]}"
        )
    rw = research_and_write(
        db=db, headline=p.title, source_excerpt=excerpt,
        matched_term=subject, today=today, tense="cronica",
    )
    if not rw.get("body_md") or len((rw["body_md"] or "").strip()) < 400:
        logger.info("  crónica insuficiente tras verificación para «%s»", subject)
        return None
    return rw


def _handle_expired(db, p: ContentProposal, today, *, dry_run: bool) -> str:
    """Evento ya pasado: reconvierte a crónica si hay material real, o cancela.
    Devuelve 'rewritten' | 'cancelled'."""
    logger.info("  ⏰ evento caducado (event_date %s < hoy %s)", p.event_date, today)
    if dry_run:
        return "rewritten"  # en dry-run no decidimos, solo informamos
    cron = _build_chronicle(db, p, today)
    if cron:
        p.title = (cron.get("title") or p.title)[:240]
        p.body_md = cron.get("body_md") or p.body_md
        p.excerpt = (cron.get("excerpt") or p.excerpt or "")[:200] or None
        if cron.get("meta_title"):
            p.meta_title = cron["meta_title"][:60]
        if cron.get("meta_description"):
            p.meta_description = cron["meta_description"][:155]
        db.commit()
        logger.info("  ↪ reconvertida a CRÓNICA en pasado")
        return "rewritten"
    # Sin crónica: no se publica nada caducado.
    p.status = "discarded"
    db.commit()
    _notify_admin(
        f"🗑 Publicación caducada cancelada: {p.title}",
        f"El evento (event_date {p.event_date}) ya pasó y no se encontró crónica. "
        f"La propuesta #{p.id} se ha descartado para no publicar algo obsoleto.",
    )
    logger.info("  ✗ cancelada (caducada sin crónica) — propuesta #%s descartada", p.id)
    return "cancelled"


def _slugify(text: str, max_len: int = 90) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    ascii_only = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return ascii_only[:max_len] or "post"


def _unique_slug(db, base: str) -> str:
    slug = base
    i = 2
    while db.execute(select(Post).where(Post.slug == slug)).scalar_one_or_none():
        slug = f"{base}-{i}"
        i += 1
    return slug


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    today = date.today()
    with SessionLocal() as db:
        due = (
            db.query(ContentProposal)
            .filter(ContentProposal.status == "scheduled")
            .filter(ContentProposal.scheduled_for.isnot(None))
            .filter(ContentProposal.scheduled_for <= today)
            .order_by(ContentProposal.scheduled_for)
            .all()
        )
        logger.info("Propuestas a materializar hoy: %d", len(due))

        for p in due:
            logger.info("[%s] %s (programada %s)", p.kind, p.title, p.scheduled_for)

            # 0. CADUCIDAD: si el evento de la noticia ya pasó, reconvertir a
            #    crónica (si hay material) o cancelar (no publicar nada obsoleto).
            expired = bool(p.event_date and p.event_date < today)
            if args.dry_run:
                if expired:
                    logger.info("  ⏰ [dry-run] evento caducado (%s)", p.event_date)
                continue
            if expired:
                if _handle_expired(db, p, today, dry_run=False) == "cancelled":
                    continue

            # 1. Asegurar borrador (normalmente ya hecho al aprobar).
            if not p.body_md:
                logger.info("  sin borrador, generando ahora (red de seguridad)")
                if not generate_proposal_draft(db, p):
                    logger.error("  no se pudo generar body para propuesta %s", p.id)
                    continue

            # 1·pre. GUARD DE POLÍTICA NUEVA: nada que no haya pasado por el pipeline
            #   actual (scoring de engagement + motor profundo) se publica. La señal
            #   es `quality_tier`: si falta, la propuesta se generó con el motor viejo
            #   (one-shot flaco → "paja"). Se REGENERA antes de los gates. Las noticias
            #   conservan el cuerpo del scraper (no hay entidad que profundizar): solo
            #   se les backfillea el score. El override del admin lo salta.
            if not p.force_publish and p.quality_tier is None:
                logger.info("  ⚠ sin quality_tier (motor viejo) → regeneración con pipeline nuevo")
                if p.kind != "news":
                    p.body_md = None  # fuerza cuerpo por el motor profundo
                if not generate_proposal_draft(db, p):
                    _notify_admin(
                        f"⏸ No publicada (regen falló): {p.title}",
                        f"La propuesta #{p.id} no tenía quality_tier (motor viejo) y la "
                        "regeneración con el pipeline nuevo falló. NO se publica; requiere "
                        "revisión manual para no sacar contenido flojo.",
                    )
                    logger.info("  ✗ regen falló → no se publica (propuesta #%s)", p.id)
                    continue
                logger.info("  ↪ regenerada (tier %s)", p.quality_tier)

            # 1b. GATE DE FOCO: nada se publica desviado del tema (relleno sobre
            #     el lugar/sede/contexto ajeno). Si se puede recortar limpio, se
            #     recorta; si no, va a revisión humana.
            review_focus = False
            subject = (p.target_keyword or p.title or "").strip()
            freport = check_focus(p.body_md, subject)
            if not freport.ok:
                if freport.trimmed_body_md:
                    p.body_md = freport.trimmed_body_md
                    db.commit()
                    logger.info("  foco: recortado (score %d, deriva: %s)",
                                freport.score, ", ".join(freport.drift_headings) or "—")
                else:
                    review_focus = True
                    logger.info("  foco BAJO (score %d) sin recorte limpio → revisión",
                                freport.score)

            # 1c. GATE DE RIGOR EDITORIAL: nada genérico/relleno se publica. Si se
            #     puede tensar, se tensa; si es flojo sin remedio (faltan HECHOS),
            #     se DESCARTA y se avisa (no se publica y punto). El override del
            #     admin (`force_publish`) lo salta — publica bajo su criterio.
            if p.force_publish:
                review_focus = False  # el admin fuerza: no bloquear por calidad
                logger.info("  ⚡ force_publish: se salta el gate de calidad")
            else:
                when = None
                if p.event_date:
                    when = "past" if p.event_date < today else "future"
                verdict = editorial_review(p.body_md, kind=p.kind, subject=subject,
                                           event_when=when)
                if verdict.verdict == "reject":
                    p.status = "discarded"
                    db.commit()
                    _notify_admin(
                        f"🗑 Descartada por rigor: {p.title}",
                        f"La propuesta #{p.id} no llega al listón editorial (score "
                        f"{verdict.score}): {'; '.join(verdict.reasons) or 'genérica/relleno'}. "
                        "No se publica por falta de sustancia/especificidad.",
                    )
                    logger.info("  ✗ DESCARTADA por rigor (score %d): %s",
                                verdict.score, "; ".join(verdict.reasons))
                    continue
                if verdict.verdict == "revise" and verdict.tightened_body_md:
                    p.body_md = verdict.tightened_body_md
                    db.commit()
                    logger.info("  rigor: tensado (score %d)", verdict.score)

            # 1d. Medios: embebe vídeos referenciados como enlace (URL desnuda).
            from app.services.text_sanitizer import embed_youtube_links
            embedded = embed_youtube_links(p.body_md)
            if embedded and embedded != p.body_md:
                p.body_md = embedded
                db.commit()

            # 2. Crear el Post copiando el borrador ya saneado/enlazado.
            slug = _unique_slug(db, _slugify(p.title))
            post = Post(
                slug=slug,
                kind=p.kind,
                status="draft",
                title=p.title[:240],
                excerpt=p.excerpt,
                body_md=p.body_md,
                meta_title=p.meta_title[:60] if p.meta_title else None,
                meta_description=p.meta_description[:155] if p.meta_description else None,
                target_keyword=p.target_keyword,
                target_keyword_slug=p.target_keyword_slug,
                content_key=p.content_key,
                source_url=p.source_url,
                source_name=p.source_name,
                hero_image_url=p.hero_image_url,
                hero_image_alt=p.hero_image_alt,
                hero_image_attribution=p.hero_image_attribution,
                hero_image_license=p.hero_image_license,
                hero_image_source_url=p.hero_image_source_url,
                entities=p.entities or [],
                event_date=p.event_date,
                video=p.video,
                videos=p.videos,
                engagement_score=p.engagement_score,
                quality_tier=p.quality_tier,
                force_publish=p.force_publish,
            )
            db.add(post)
            db.commit()
            db.refresh(post)

            # 3. GATE FACTUAL antes de publicar. Auto-corrige las contradicciones
            #    canónicas de BD (canción↔álbum↔año); si la verificación web
            #    detecta algo dudoso (to_review), el post NO se auto-publica: va a
            #    revisión humana. Solo lo que pasa LIMPIO se publica solo.
            report = check_body(db, post.body_md, use_web=True)
            skipped: list = []
            if report.autofixes:
                fixed, skipped = correct_body(db, post.body_md, report)
                if fixed and fixed != post.body_md:
                    post.body_md = fixed
                    db.commit()
                    db.refresh(post)
                    logger.info("  fact-check: %d hecho(s) corregido(s) contra BD",
                                len(report.autofixes) - len(skipped))

            # 3b. GATE DE CITAS DE LETRA (determinista, BLOQUEANTE, NO evadible ni
            #     con force_publish): un verso inventado o una cita de una canción
            #     sin letra verificable en el corpus NO se publica JAMÁS. La zona
            #     gris (coincidencia parcial / posible misatribución) va a revisión.
            from app.services.lyric_guard import check_lyrics
            lyric_report = check_lyrics(db, post.body_md)
            if lyric_report.blocking:
                db.delete(post)
                p.status = "discarded"
                db.commit()
                detalle = "; ".join(f"«{v.quote[:60]}» → {v.reason}"
                                    for v in lyric_report.blocking)
                _notify_admin(
                    f"🗑 Descartada por CITA NO VERAZ: {p.title}",
                    f"La propuesta #{p.id} cita versos que no existen en la letra real "
                    f"(o de una canción sin letra verificable): {detalle}. No se publica "
                    "(regla de veracidad, no evadible ni con force_publish).",
                )
                logger.info("  ✗ DESCARTADA por citas no veraces: %s", detalle)
                continue

            # A revisión humana si la web detecta algo dudoso (to_review), si algún
            # hecho refutado no se pudo corregir limpio (skipped → reformular), si
            # una cita de letra queda en zona gris, o si el gate de FOCO marcó deriva.
            # La VERACIDAD (datos + citas) NO es evadible por force_publish: siempre
            # va a revisión humana. force_publish solo salta rigor/foco (gustos).
            needs_review = report.to_review + skipped
            lyric_review = lyric_report.to_review
            if needs_review or lyric_review or review_focus:
                for v in needs_review:
                    logger.info("  fact-check REVISAR: %s · %s", v.claim.type, v.claim.subject)
                for v in lyric_review:
                    logger.info("  cita REVISAR: «%s» · %s", v.quote[:50], v.reason)
                if review_focus:
                    logger.info("  foco REVISAR: deriva no recortable")
                propose_for_review(db, post)
                p.status = "used"
                p.post_id = post.id
                db.commit()
                logger.info("  ⚠ a revisión humana (%d dato(s), %d cita(s)%s): /blog/%s",
                            len(needs_review), len(lyric_review),
                            ", +foco" if review_focus else "", slug)
                continue

            # 4. Limpio → publicar (revalidate de Next; el email es el digest dominical).
            #    factcheck=False y rigor=False: los gates de arriba ya verificaron
            #    (capa web + foco + rigor editorial); no repetir.
            auto_publish_post(db, post, factcheck=False, rigor=False)
            p.status = "used"
            p.post_id = post.id
            db.commit()
            logger.info("  ✓ publicado como /blog/%s", slug)


if __name__ == "__main__":
    main()
