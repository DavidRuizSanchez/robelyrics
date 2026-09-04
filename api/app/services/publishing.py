"""Servicio de publicación.

Política editorial: **nada se publica automáticamente**. Los scripts cron
crean posts en estado `pending_review` y envían email al admin con botones
de aprobar/rechazar (firmados con JWT) + enlace al panel admin. La
publicación efectiva ocurre cuando el admin aprueba — desde el email o
desde el panel.

API:
- `propose_for_review(post, notify=True)` → setea pending_review y manda
  mail con preview + acciones. Llamado por todos los scripts cron.
- `auto_publish_post(post)` → marca published y hace revalidate Next.
  Llamado por el endpoint admin (panel o mail one-click). El email NO se
  manda aquí: la newsletter es un único digest semanal (cron dominical
  `send_newsletter` → `dispatch_to_all_confirmed`).
- `schedule_or_publish(post)` → DEPRECATED, alias de propose_for_review
  por compatibilidad con scripts viejos.
- `flush_scheduled_due(db)` → cron diario que promueve `scheduled` a
  `published` (legacy del flujo anterior con cap móvil; mantenido por si
  queda algún post encolado).
"""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import TypedDict

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import Post

logger = logging.getLogger(__name__)

# Techo de publicaciones por semana natural y ventana móvil para el cap.
WEEKLY_CAP = 4
WINDOW_DAYS = 7

# Días de la semana para el reparto automático (lunes=0): lunes, martes, jueves,
# sábado. El n-ésimo post de la semana cae en PUBLISH_SLOT_DAYS[n].
PUBLISH_SLOT_DAYS = [1, 3, 5, 0]

# Kinds que ignoran el cap porque tienen fecha calendario obligatoria.
CAP_EXEMPT_KINDS = {"anniversary", "album-anniversary"}

# Antelación mínima (días) para publicar una noticia de un evento ANTES de que
# ocurra. Una pieza "a futuro" debe salir con margen, no el mismo día.
EVENT_LEAD_DAYS = 3


def recommended_from_event(event_date, today, *, lead_days: int = EVENT_LEAD_DAYS):
    """Fecha SUGERIDA de publicación para una noticia con `event_date` futura:
    `event_date − lead_days`, nunca antes de mañana. Devuelve None si el evento
    ya pasó o no hay fecha (no se sugiere nada; la caducidad se ocupa del resto)."""
    from datetime import date as _date
    from datetime import timedelta as _td

    if not event_date or not isinstance(event_date, _date):
        return None
    if event_date <= today:
        return None
    suggested = event_date - _td(days=lead_days)
    tomorrow = today + _td(days=1)
    return max(suggested, tomorrow)


class PublishResult(TypedDict):
    action: str  # "published" | "scheduled"
    post_id: int
    scheduled_for: datetime | None


# --------------------------------------------------------------------------- #
# Núcleo: scheduler
# --------------------------------------------------------------------------- #
def _now() -> datetime:
    return datetime.now(UTC)


def _occupied_dates(db: Session, *, look_ahead_days: int = 60) -> list[datetime]:
    """Devuelve las fechas relevantes para calcular el cap.

    Incluye:
      - Publicados en los últimos 7+ días (necesario para ver si llenan ventana).
      - Scheduled futuros (porque cuentan al hueco que ocuparán).
    Excluye aniversarios — no cuentan contra el cap.
    """
    now = _now()
    horizon_past = now - timedelta(days=WINDOW_DAYS + 1)
    horizon_future = now + timedelta(days=look_ahead_days)

    rows = (
        db.query(Post.kind, Post.status, Post.published_at, Post.scheduled_for)
        .filter(
            or_(
                (Post.status == "published") & (Post.published_at >= horizon_past),
                (Post.status == "scheduled") & (Post.scheduled_for > now) & (Post.scheduled_for < horizon_future),
            )
        )
        .all()
    )
    dates: list[datetime] = []
    for kind, status, pub_at, sched_at in rows:
        if kind in CAP_EXEMPT_KINDS:
            continue
        dt = pub_at if status == "published" else sched_at
        if dt is not None:
            dates.append(dt)
    dates.sort()
    return dates


def _next_publish_slot(db: Session) -> datetime:
    """Primer instante a partir de `now()` donde, contando publicados y
    scheduled, la ventana de 7 días previos tiene `< WEEKLY_CAP` posts no
    exentos.
    """
    now = _now()
    dates = _occupied_dates(db)
    candidate = now

    # Avanza candidate iterativamente. Cada iteración salta al momento en que
    # el siguiente post deja la ventana de 7 días.
    for _ in range(50):  # cota de seguridad
        window_start = candidate - timedelta(days=WINDOW_DAYS)
        in_window = [d for d in dates if window_start < d <= candidate]
        if len(in_window) < WEEKLY_CAP:
            return candidate
        # Lleno. Avanza al momento en que sale el más antiguo de la ventana.
        oldest_in_window = min(in_window)
        candidate = oldest_in_window + timedelta(days=WINDOW_DAYS, minutes=1)

    # Fallback defensivo
    logger.warning("publishing._next_publish_slot saturó 50 iteraciones")
    return now + timedelta(days=WINDOW_DAYS)


# --------------------------------------------------------------------------- #
# Hooks post-publicación
# --------------------------------------------------------------------------- #
def _revalidate_next(slug: str) -> None:
    """Pide a Next.js que revalide /blog y /blog/{slug}. No bloquea si falla."""
    token = os.environ.get("REVALIDATE_TOKEN")
    if not token:
        logger.info("REVALIDATE_TOKEN no configurado, salto revalidate")
        return
    base = os.environ.get("WEB_INTERNAL_URL", "http://web:3000").rstrip("/")
    url = f"{base}/api/revalidate"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                url,
                headers={"X-Revalidate-Token": token},
                json={"paths": ["/blog", f"/blog/{slug}"], "tags": ["posts"]},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Revalidate failed for /blog/%s: %s", slug, exc)


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
def propose_for_review(
    db: Session, post: Post, *, notify: bool = True
) -> PublishResult:
    """Pone el post en `pending_review` y manda email al admin (si notify).

    También linkifica el `body_md` reemplazando la primera mención de cada
    entidad detectada por un link a su página local (si existe en el
    corpus) o a Wikidata. Esto se hace ANTES del primer commit para que
    el admin vea el contenido ya enlazado en el panel y en el mail.

    Idempotente: si ya está en pending_review, no rompe.
    """
    if post.status in {"published", "rejected"}:
        logger.info(
            "Post %s ya está en estado terminal (%s); no se propone",
            post.id, post.status,
        )
        return {
            "action": post.status,
            "post_id": post.id,
            "scheduled_for": None,
        }

    # Normalizar jerarquía de headings (H1→H2…) y enlazado interno automático
    # a todo el corpus (máx. 4 enlaces, los más relevantes).
    if post.body_md:
        from app.services.entity_resolver import (
            autolink_corpus,
            build_corpus_index,
            load_link_stats,
        )
        from app.services.text_sanitizer import normalize_headings
        new_body = normalize_headings(post.body_md) or post.body_md
        new_body = autolink_corpus(
            new_body, build_corpus_index(db), max_links=4,
            link_stats=load_link_stats(),
        )
        # Después del autolink, no antes: el autolink también mete URLs (esas,
        # construidas desde la BD, pasan limpias) y lo que hay que cazar son las
        # que se inventó el LLM al escribir el cuerpo.
        from app.services.url_resolver import guard_internal_links

        _links = guard_internal_links(db, new_body)
        if _links.changed:
            logger.info("Post %s: enlaces internos → %s", post.id, _links.summary())
            new_body = _links.body_md
        if new_body != post.body_md:
            post.body_md = new_body
            logger.info("Post %s: headings normalizados + autolink corpus", post.id)

    if post.status != "pending_review":
        post.status = "pending_review"
    db.commit()
    db.refresh(post)

    if notify:
        _notify_admin_review(db, post)

    return {"action": "pending_review", "post_id": post.id, "scheduled_for": None}


def _notify_admin_review(db: Session, post: Post) -> None:
    """Manda un email al admin con TODOS los posts pending_review (incluido
    el que se acaba de crear), con botones aprobar/rechazar firmados.
    Si falla, log warning pero no aborta (el post queda en pending_review
    igualmente)."""
    admin_email = os.environ.get("ADMIN_EMAIL")
    if not admin_email:
        logger.info("ADMIN_EMAIL no configurado, salto notify admin review")
        return

    site_url = os.environ.get("SITE_URL", "https://entreinteriores.com").rstrip("/")
    admin_panel_url = f"{site_url}/biblioteca/admin/blog"

    from app.services.auth import create_admin_action_token
    from app.services.email import (
        EmailError,
        render_admin_review_email,
        send_email,
    )

    pendings = (
        db.query(Post)
        .filter(Post.status == "pending_review")
        .order_by(Post.created_at.desc())
        .limit(10)
        .all()
    )
    if not pendings:
        return

    kind_label = {
        "editorial": "Editorial",
        "news": "Noticia",
        "anniversary": "Efeméride",
        "album-anniversary": "Aniversario de disco",
        "spotlight": "Spotlight",
        "evergreen": "Evergreen",
    }

    items = []
    for p in pendings:
        approve_token = create_admin_action_token(p.id, "approve")
        reject_token = create_admin_action_token(p.id, "reject")
        items.append({
            "title": p.title,
            "kind_label": kind_label.get(p.kind, p.kind),
            "excerpt": p.excerpt,
            "source_name": p.source_name,
            "source_url": p.source_url,
            "approve_url": f"{site_url}/api/public/admin-action?token={approve_token}",
            "reject_url": f"{site_url}/api/public/admin-action?token={reject_token}",
            "admin_url": f"{site_url}/biblioteca/admin/blog",
        })

    html, text = render_admin_review_email(items, admin_panel_url)
    subject = (
        f"📰 Una entrada para revisar — «{pendings[0].title}»"
        if len(pendings) == 1
        else f"📰 {len(pendings)} entradas para revisar en Entre Interiores"
    )
    try:
        send_email(to=admin_email, subject=subject, html=html, text=text)
        logger.info("Admin review email enviado (%d pendings)", len(pendings))
    except EmailError as exc:
        logger.warning("Admin review email failed: %s", exc)


def auto_publish_post(
    db: Session, post: Post, *, factcheck: bool = True, rigor: bool = True
) -> PublishResult:
    """Marca el post como publicado y revalida Next.js.

    NO manda email: la newsletter es un único digest semanal (cron dominical
    `send_newsletter`). Llamado:
      - Desde el endpoint admin (panel `/admin/posts/{id}/publish`).
      - Desde `/public/admin-action?token=...` (one-click desde email).
      - Desde materialize_proposals y flush_scheduled_due.

    `factcheck`: red de seguridad anti-alucinación común a TODOS los caminos de
    publicación (efeméride directa, aprobación manual, cron). Corrige errores de
    catálogo (canción↔álbum↔año) contra la BD, determinista y quirúrgico. Quien
    ya verificó antes (materialize_proposals) lo pasa en False para no repetir.

    `rigor`: gate editorial BLOQUEANTE (el "editor jefe"). Si la pieza es genérica/
    relleno y no se puede tensar, NO se publica: se enruta a `pending_review`. Quien
    ya lo corrió antes (materialize_proposals) lo pasa en False.
    """
    if factcheck and post.body_md:
        try:
            from app.services.fact_check import check_body, correct_body
            # Para noticias activamos la capa web (el evento/protagonista no está
            # en el catálogo): así el camino de publicación manual también pasa
            # un control real, no solo el canónico de BD.
            rep = check_body(db, post.body_md, use_web=(post.kind == "news"))
            if rep.autofixes:
                fixed, skipped = correct_body(db, post.body_md, rep)
                if fixed and fixed != post.body_md:
                    post.body_md = fixed
                    db.flush()
                    logger.info(
                        "auto_publish: %d hecho(s) de catálogo corregido(s) en post %s",
                        len(rep.autofixes) - len(skipped), post.id,
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("auto_publish fact-check falló: %s", exc)

    # Gate de FOCO para noticias: recorta la deriva temática (relleno sobre el
    # lugar/sede) antes de publicar. Best-effort: no bloquea, solo mejora.
    if factcheck and post.kind == "news" and post.body_md:
        try:
            from app.services.focus_check import check_focus
            subject = (post.target_keyword or post.title or "").strip()
            fr = check_focus(post.body_md, subject)
            if not fr.ok and fr.trimmed_body_md:
                post.body_md = fr.trimmed_body_md
                db.flush()
                logger.info("auto_publish: foco recortado en post %s (score %d)",
                            post.id, fr.score)
        except Exception as exc:  # noqa: BLE001
            logger.warning("auto_publish focus-check falló: %s", exc)

    # Embebe vídeos referenciados como enlace (URL desnuda → reproductor).
    if post.body_md:
        try:
            from app.services.text_sanitizer import embed_youtube_links
            emb = embed_youtube_links(post.body_md)
            if emb and emb != post.body_md:
                post.body_md = emb
                db.flush()
        except Exception as exc:  # noqa: BLE001
            logger.warning("auto_publish embed-youtube falló: %s", exc)

    # Gate de ENLACES INTERNOS (universal, NO bloqueante): una ruta inventada por
    # el LLM se reapunta a la real o se desenlaza. Va aquí, en el tronco común de
    # TODOS los caminos de publicación (efeméride, manual, cron), que es donde
    # están el resto de cortafuegos. Los cuatro que ya había miran el TEXTO;
    # este es el único que mira la URL.
    if post.body_md:
        from app.services.url_resolver import guard_internal_links

        _links = guard_internal_links(db, post.body_md)
        if _links.changed:
            logger.info("auto_publish: enlaces del post %s → %s",
                        post.id, _links.summary())
            post.body_md = _links.body_md
            db.flush()

    # Gate de RIGOR editorial (universal, BLOQUEANTE): si la pieza es genérica o
    # pura paja y no se puede salvar tensando, NO se publica → revisión humana.
    # El override del admin (`force_publish`) lo salta.
    if rigor and post.body_md and not getattr(post, "force_publish", False):
        try:
            from app.services.editorial_review import review as editorial_review
            subject = (post.target_keyword or post.title or "").strip()
            when = None
            if post.kind == "news" and post.event_date:
                when = "past" if post.event_date < _now().date() else "future"
            v = editorial_review(post.body_md, kind=post.kind, subject=subject, event_when=when)
            if v.verdict == "reject":
                logger.info("auto_publish: RIGOR rechaza post %s (score %d): %s",
                            post.id, v.score, "; ".join(v.reasons))
                return propose_for_review(db, post)
            if v.verdict == "revise" and v.tightened_body_md:
                post.body_md = v.tightened_body_md
                db.flush()
                logger.info("auto_publish: RIGOR tensó post %s (score %d)", post.id, v.score)
        except Exception as exc:  # noqa: BLE001
            logger.warning("auto_publish rigor falló: %s", exc)

    # Gate de CITAS DE LETRA (universal, BLOQUEANTE, NO evadible ni con
    # force_publish): último cortafuegos común a TODOS los caminos de publicación
    # (efeméride directa, publicación manual, cron). Un verso inventado o una cita
    # de canción sin letra verificable NO se publica jamás: se enruta a revisión.
    # Determinista y barato; corre siempre (independiente de factcheck/rigor).
    if post.body_md:
        try:
            from app.services.lyric_guard import check_lyrics
            lr = check_lyrics(db, post.body_md)
            if lr.blocking or lr.to_review:
                logger.warning("auto_publish: CITAS bloquean post %s (%s) → revisión",
                               post.id, lr.summary())
                return propose_for_review(db, post)
        except Exception as exc:  # noqa: BLE001
            logger.warning("auto_publish lyric-guard falló: %s", exc)

    # Gate de RELEVANCIA de la IMAGEN hero (universal): una foto que no muestra al
    # sujeto NO llega a producción. Cortafuegos común a TODOS los caminos, incluidos
    # los que fijan el hero fuera de build_unique_hero (efeméride, scrape_news, admin
    # desde URL). Si falla, se REGENERA a imagen relevante (degrada a arte propio,
    # on-topic por construcción); si ni así hay imagen verificable, se publica SIN
    # imagen (mejor un post sin foto que con una foto equivocada).
    if post.hero_image_url:
        try:
            from app.services.hero_guard import verify_hero
            from app.services.hero_io import apply_hero, read_hero
            subject = (post.target_keyword or post.title or "").strip()
            verdict = verify_hero(read_hero(post), subject=subject, entities=post.entities or [])
            if not verdict.ok:
                logger.warning("auto_publish: HERO irrelevante en post %s (%s) → regenerando",
                               post.id, verdict.reason)
                from app.services.blog_hero import build_unique_hero, used_hero_urls
                used = used_hero_urls(db) - {post.hero_image_url}
                new_hero = build_unique_hero(
                    db, post.entities or [], subject, used=used, alt_label=post.title,
                )
                apply_hero(post, new_hero)  # verificado, o None → sin imagen
                db.flush()
        except Exception as exc:  # noqa: BLE001
            logger.warning("auto_publish hero-guard falló: %s", exc)

    if post.status != "published":
        post.status = "published"
        post.published_at = _now()
        post.scheduled_for = None
        db.flush()
    db.commit()
    db.refresh(post)

    _revalidate_next(post.slug)

    return {"action": "published", "post_id": post.id, "scheduled_for": None}


def schedule_or_publish(db: Session, post: Post) -> PublishResult:
    """DEPRECATED: alias de `propose_for_review`. Nada se publica automáticamente.

    Mantenido para compatibilidad con scripts/llamadores anteriores; nuevos
    usos deben llamar directamente a `propose_for_review`.
    """
    return propose_for_review(db, post)


def flush_scheduled_due(db: Session) -> dict[str, int]:
    """Publica todos los posts en estado `scheduled` cuyo `scheduled_for`
    ya pasó. Llamado por cron diario.
    """
    now = _now()
    due = (
        db.query(Post)
        .filter(Post.status == "scheduled")
        .filter(Post.scheduled_for.isnot(None))
        .filter(Post.scheduled_for <= now)
        .order_by(Post.scheduled_for)
        .all()
    )
    published = 0
    for post in due:
        # Re-check del cap antes de publicar (puede que se haya llenado por
        # otras vías mientras estaba encolado).
        seven_ago = now - timedelta(days=WINDOW_DAYS)
        cnt = (
            db.query(Post)
            .filter(Post.status == "published")
            .filter(Post.published_at >= seven_ago)
            .filter(~Post.kind.in_(CAP_EXEMPT_KINDS))
            .count()
        )
        if cnt >= WEEKLY_CAP:
            new_slot = _next_publish_slot(db)
            post.scheduled_for = new_slot
            db.commit()
            logger.info(
                "Post %s re-encolado a %s (cap saturado al despertar)",
                post.id, new_slot.isoformat(),
            )
            continue
        auto_publish_post(db, post)
        published += 1
    return {"due": len(due), "published": published}
