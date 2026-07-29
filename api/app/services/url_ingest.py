"""Alta manual de una noticia del blog a partir de una URL.

Vive fuera del router porque el trabajo NO cabe en una petición HTTP: el motor
tarda de 2 a 4 minutos (planifica, investiga, escribe sección a sección
verificando cada una y, si el gate de rigor la rechaza, reintenta con
investigación reforzada) y Cloudflare corta a los 100 s. Medido en producción:
264,8 s → el admin recibía un `524` y no veía nunca el resultado, ni la propuesta
creada ni las razones del rechazo.

Ahora el router solo encola un `UrlIngestJob` y llama a `run_job` en segundo
plano: corre en el servidor, así que sobrevive a cerrar la pestaña, y deja el
resultado en BD para que el panel lo recoja cuando vuelva.
"""
from __future__ import annotations

import logging
from datetime import date as _date
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.db.models import ContentProposal, UrlIngestJob
from scripts.research.fetch_blogs import HEADERS, extract_article_text

logger = logging.getLogger(__name__)

# Mínimo de texto para que la reescritura tenga con qué trabajar. Mismo umbral
# para lo scrapeado y para lo pegado a mano.
MIN_ARTICLE_CHARS = 200

# Códigos con los que un medio dice "no sirvo a bots". Nuestro UA es
# identificativo y no se disfraza de navegador (Responsible Builder Policy), así
# que estos son un no definitivo, no un fallo transitorio: la salida es pegar el
# texto a mano. Caso real: el WAF de deia.eus responde 406 a todo lo que no
# parezca un navegador, incluso a su propio robots.txt.
BOT_BLOCKED = {401, 403, 406, 429, 451}
PASTE_HINT = (
    "abre el artículo en el navegador, copia el texto y pégalo en "
    "«cuerpo del artículo»"
)


class IngestError(Exception):
    """Fallo con un mensaje que el panel puede mostrar tal cual."""

    def __init__(self, message: str, *, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class RigorRejected(Exception):
    """El editor jefe tumbó la pieza. Lleva el veredicto para poder explicarlo."""

    def __init__(self, score: int, reasons: list[str], *, boosted: bool):
        super().__init__("rechazada por el gate de rigor")
        self.score = score
        self.reasons = reasons
        self.boosted = boosted


# --------------------------------------------------------------------------- #
# Obtención del texto
# --------------------------------------------------------------------------- #
def scrape_article(url: str) -> tuple[str, str]:
    """Descarga una URL y devuelve (título, texto del artículo).

    Reutiliza el extractor de `fetch_blogs`. La validación SSRF la hace el schema
    del router (`_validate_external_url`)."""
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            r = client.get(url, headers=HEADERS)
    except httpx.HTTPError as e:
        raise IngestError(f"error al descargar la URL: {e}") from e

    if r.status_code in BOT_BLOCKED:
        raise IngestError(
            f"el medio bloquea la descarga automática (HTTP {r.status_code}); "
            f"{PASTE_HINT}"
        )
    if r.status_code != 200:
        raise IngestError(f"la URL devolvió {r.status_code}")

    text = extract_article_text(r.text)
    if not text or len(text) < MIN_ARTICLE_CHARS:
        raise IngestError(
            "no se ha podido extraer un cuerpo aprovechable "
            f"(<{MIN_ARTICLE_CHARS} caracteres): muro de pago o texto montado por "
            f"JavaScript; {PASTE_HINT}"
        )

    title = ""
    soup = BeautifulSoup(r.text, "html.parser")
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title and soup.h1:
        title = soup.h1.get_text(strip=True)
    return title[:240], text


def pasted_article(text: str, topic: str | None) -> tuple[str, str]:
    """Valida el texto pegado a mano y devuelve (titular, texto).

    El titular sale de la primera línea si tiene pinta de serlo (al copiar un
    artículo suele venir arriba); si no, de la pista del tema. Con reescritura da
    igual quedarse corto —el motor escribe su propio titular—, pero sin ella es lo
    único que hay."""
    text = (text or "").strip()
    if len(text) < MIN_ARTICLE_CHARS:
        raise IngestError(
            f"el texto pegado se queda corto ({len(text)} caracteres, hacen falta "
            f"{MIN_ARTICLE_CHARS}): pega el artículo entero"
        )
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    # Si el texto viene de un markdown, la primera línea trae los '#' del heading:
    # sin esto el titular de la propuesta queda como «## Umore Ona: …».
    first = first.lstrip("#").strip()
    headline = first if 15 <= len(first) <= 160 else (topic or "").strip()
    return headline[:240], text


# --------------------------------------------------------------------------- #
# Gate editorial
# --------------------------------------------------------------------------- #
def editorial_gate(
    body_md: str, subject: str, material: str | None = None, db=None,
):
    """Pasa una pieza recién escrita por los mismos gates que el cron y la
    publicación: foco (recorta deriva, no bloquea), rigor (editor jefe) y
    enlaces internos (rutas inventadas → la real, o desenlazadas).

    Devuelve `(body_final, verdict)`. El alta manual NO los tenía —viven en
    `publishing.auto_publish_post` y en `scripts.blog.materialize_proposals`—, así
    que el admin veía en el panel texto sin juzgar y solo se enteraba de que era
    paja al leerlo. `verdict` es None si el gate no pudo correr."""
    from app.services.editorial_review import review as editorial_review
    from app.services.focus_check import check_focus

    try:
        fr = check_focus(body_md, subject)
        if not fr.ok and fr.trimmed_body_md:
            body_md = fr.trimmed_body_md
    except Exception as exc:  # noqa: BLE001 — best-effort, nunca bloquea
        logger.warning("[url_ingest] focus-check falló: %s", exc)

    try:
        v = editorial_review(body_md, kind="news", subject=subject, material=material)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[url_ingest] rigor falló: %s", exc)
        v = None

    if v is not None and v.verdict == "revise" and v.tightened_body_md:
        body_md = v.tightened_body_md

    # Enlaces internos: se validan aquí, antes de que la propuesta se guarde, para
    # que el admin no vea en el panel un texto con rutas inventadas. Necesita
    # sesión, así que solo corre cuando se la pasan.
    if db is not None:
        from app.services.url_resolver import guard_internal_links

        enlaces = guard_internal_links(db, body_md)
        if enlaces.changed:
            logger.info("[url_ingest] enlaces internos → %s", enlaces.summary())
            body_md = enlaces.body_md

    return body_md, v


# --------------------------------------------------------------------------- #
# El trabajo
# --------------------------------------------------------------------------- #
def ingest(
    db, *, url: str, topic: str | None, body_text: str | None,
    rewrite: bool, force: bool,
) -> dict[str, Any]:
    """Crea (o retoma) la propuesta. Lanza IngestError / RigorRejected.

    Devuelve {proposal_id, title, rewritten, warning}."""
    from app.services.content_dedup import (
        NEWS_RECENCY_DAYS,
        content_key_for,
        is_duplicate,
    )

    # Si el admin pegó el texto, ese manda: no se descarga nada (es la salida para
    # medios que bloquean al bot o esconden el cuerpo tras un muro).
    if (body_text or "").strip():
        title_scraped, text = pasted_article(body_text or "", topic)
    else:
        title_scraped, text = scrape_article(url)

    # Dedup por URL exacta. `source_url` es UNIQUE en BD, así que dos propuestas de
    # la misma fuente no pueden convivir: o se corta, o se reescribe la que hay.
    # Una propuesta VIVA manda y se corta diciendo dónde está (el id sale en el
    # panel). Una DESCARTADA no puede bloquear la URL para siempre —el mismo
    # artículo admite otro enfoque más adelante—, así que con `force` se RETOMA esa
    # misma fila con el contenido nuevo.
    existing = (
        db.query(ContentProposal)
        .filter(ContentProposal.source_url == url)
        .order_by(ContentProposal.id.desc())
        .first()
    )
    revive: ContentProposal | None = None
    if existing is not None:
        where = {
            "proposed": "está en «por validar»",
            "approved": "está en «aprobadas»",
            "scheduled": "está en «programadas»",
            "used": "ya se publicó",
            "discarded": "está en «descartadas»",
        }.get(existing.status, f"está en estado {existing.status}")
        if existing.status != "discarded":
            raise IngestError(
                f"ya existe una propuesta con esa URL: #{existing.id} "
                f"«{existing.title}», {where}",
                status=409,
            )
        if not force:
            raise IngestError(
                f"esa URL ya se usó en la propuesta #{existing.id} "
                f"«{existing.title}», que descartaste; marca 'forzar' para "
                "retomarla con el contenido nuevo",
                status=409,
            )
        revive = existing

    warning: str | None = None
    # ¿Pasó el texto por el motor editorial? Solo es False cuando se guarda en
    # crudo. Un rechazo de rigor forzado SÍ está reescrito, aunque lleve aviso.
    rewritten_ok = True
    entities: list = []
    hero_pkg: dict | None = None
    event_date = None
    video = None

    if rewrite:
        from app.services.news_research import research_and_write

        matched = (topic or title_scraped or "Robe Extremoduro").strip()

        def _write(boost: bool) -> dict:
            try:
                return research_and_write(
                    db=db, headline=title_scraped or matched, source_excerpt=text,
                    matched_term=matched, today=_date.today(), boost=boost,
                )
            except Exception as exc:  # noqa: BLE001
                raise IngestError(
                    f"la reescritura editorial falló: {exc}", status=502
                ) from exc

        rw = _write(boost=False)

        # Gate de rigor con UNA segunda oportunidad: si el editor jefe la rechaza,
        # se reescribe con investigación reforzada (`boost`) y se vuelve a juzgar.
        # Potenciar es traer MÁS MATERIAL REAL, nunca aflojar el listón.
        if rw.get("is_relevant", True) and rw.get("title"):
            boosted = False
            verdict = None
            for intento in (0, 1):
                judged, verdict = editorial_gate(
                    rw.get("body_md") or "", matched, db=db,
                )
                rw["body_md"] = judged
                if verdict is None or verdict.verdict != "reject":
                    break
                if intento == 0:
                    rw2 = _write(boost=True)
                    if not (rw2.get("is_relevant", True) and rw2.get("title")):
                        break  # el refuerzo no dio ni para reescribirla
                    rw, boosted = rw2, True
            if verdict is not None and verdict.verdict == "reject":
                if not force:
                    raise RigorRejected(
                        verdict.score, list(verdict.reasons or []), boosted=boosted
                    )
                # Válvula: el gate es DURÍSIMO (rechaza piezas comparables a las ya
                # publicadas), así que un rechazo no puede dejar al admin sin poder
                # subir nada. Con `force` entra igual, pero con el veredicto colgado
                # para leerla sabiendo lo que hay. El gate de la publicación sigue
                # en pie: esto no mete nada en la web.
                warning = (
                    f"el editor jefe la rechaza (rigor {verdict.score}/100) y la has "
                    "forzado: " + "; ".join(list(verdict.reasons or [])[:3])
                )

        if not rw.get("is_relevant", True) or not rw.get("title"):
            # El clasificador no la ve del universo Robe. No se descarta (el admin
            # la subió a propósito): se guarda en crudo con un aviso para revisión.
            # Único caso en que NO hay reescritura (un rechazo forzado sí la tuvo).
            rewritten_ok = False
            warning = (
                "el clasificador no la ve claramente del universo Robe/Extremoduro; "
                "se ha guardado el texto sin reescribir — revísala con cuidado"
            )
            title = title_scraped or matched
            body_md = f"{text}\n"
            excerpt = text[:200]
            meta_title = title[:60]
            meta_description = text[:155]
        else:
            title = rw["title"][:240]
            body_md = rw["body_md"]
            excerpt = (rw.get("excerpt") or "")[:200]
            meta_title = (rw.get("meta_title") or "")[:60]
            meta_description = (rw.get("meta_description") or "")[:155]
            event_date = rw.get("event_date")  # date o None (solo si explícita)
            video = rw.get("video")  # {youtube_id,...} o None
            entities = [
                e for e in (rw.get("entities") or [])
                if isinstance(e, dict) and e.get("name")
            ]
            hero_pkg = rw.get("hero")  # paquete coherente {url,alt,...} o None
            if hero_pkg:
                try:
                    from app.services.instagram import cloudinary_upload
                    hosted = cloudinary_upload.upload(
                        hero_pkg["url"], folder="entreinteriores-art"
                    )
                    hero_pkg = {**hero_pkg, "url": hosted,
                                "source": hero_pkg.get("source") or hero_pkg["url"]}
                except Exception:  # noqa: BLE001 — la foto es opcional
                    hero_pkg = None
    else:
        if not title_scraped:
            raise IngestError(
                "no hay título: escríbelo en «tema» o activa la reescritura "
                "editorial para que lo redacte el motor"
            )
        title = title_scraped
        body_md = f"{text}\n"
        excerpt = text[:200]
        meta_title = title[:60]
        meta_description = text[:155]

    # Dedup por evento/tema (otra fuente del mismo hecho), salvo `force`.
    ckey = content_key_for("news", title=title)
    if not force and is_duplicate(db, ckey, recency_days=NEWS_RECENCY_DAYS):
        raise IngestError(
            "ya hay una propuesta o post reciente del mismo tema; "
            "marca 'forzar' si quieres crearla igualmente",
            status=409,
        )

    # Fecha sugerida: si hay evento futuro, publicar con antelación (event−3 días).
    from app.services.publishing import recommended_from_event
    recommended_date = recommended_from_event(event_date, _date.today())

    fields = dict(
        kind="news",
        title=title,
        angle="Subida manual desde URL",
        body_md=body_md,
        excerpt=excerpt,
        meta_title=meta_title,
        meta_description=meta_description,
        # source_url para referencia interna; source_name=None (no acreditamos al
        # medio: la investigación/reescritura es nuestra, igual que en scrape_news).
        source_url=url,
        source_name=None,
        hero_image_url=(hero_pkg or {}).get("url"),
        hero_image_alt=(hero_pkg or {}).get("alt"),
        hero_image_attribution=(hero_pkg or {}).get("attribution"),
        hero_image_license=(hero_pkg or {}).get("license"),
        hero_image_source_url=(hero_pkg or {}).get("source"),
        entities=entities,
        content_key=ckey,
        event_date=event_date,
        recommended_date=recommended_date,
        video=video,
        status="proposed",
    )

    rewritten = bool(rewrite and rewritten_ok)

    if revive is not None:
        # Se reescribe la descartada entera y vuelve a «por validar»: el UNIQUE de
        # source_url no deja tener dos, y así no queda un duplicado zombi.
        was = revive.title
        for k, v in fields.items():
            setattr(revive, k, v)
        revive.angle = "Subida manual desde URL (retomada)"
        revive.scheduled_for = None
        proposal = revive
        warning = (
            f"se ha retomado la propuesta #{revive.id}, que estaba descartada "
            f"(«{was}»): vuelve a «por validar» con el contenido nuevo"
            + (f". {warning}" if warning else "")
        )
    else:
        proposal = ContentProposal(**fields)
        db.add(proposal)

    db.commit()
    db.refresh(proposal)
    return {
        "proposal_id": proposal.id,
        "title": title,
        "rewritten": rewritten,
        "warning": warning,
    }


def run_job(job_id: int) -> None:
    """Ejecuta un `UrlIngestJob` encolado. Pensado para BackgroundTasks: abre su
    PROPIA sesión (la del request ya está cerrada cuando esto corre) y nunca
    propaga excepciones — cualquier fallo se cuenta en el propio job."""
    from sqlalchemy import func as _func

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        job = db.get(UrlIngestJob, job_id)
        if job is None:
            logger.warning("[url_ingest] job %s no existe", job_id)
            return
        try:
            out = ingest(
                db, url=job.url, topic=job.topic, body_text=job.body_text,
                rewrite=job.rewrite, force=job.force,
            )
            job.status = "done"
            job.proposal_id = out["proposal_id"]
            job.title = out["title"]
            job.rewritten = out["rewritten"]
            job.warning = out["warning"]
        except RigorRejected as rej:
            db.rollback()
            job = db.get(UrlIngestJob, job_id)
            job.status = "rejected"
            job.score = rej.score
            job.reasons = rej.reasons
            job.boosted = rej.boosted
        except IngestError as err:
            db.rollback()
            job = db.get(UrlIngestJob, job_id)
            job.status = "failed"
            job.error = err.message
        except Exception as exc:  # noqa: BLE001 — el job siempre termina contando algo
            logger.exception("[url_ingest] job %s reventó", job_id)
            db.rollback()
            job = db.get(UrlIngestJob, job_id)
            job.status = "failed"
            job.error = f"error inesperado: {exc}"
        job.finished_at = _func.now()
        db.commit()
    finally:
        db.close()
