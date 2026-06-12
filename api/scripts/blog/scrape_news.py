"""Consumidor de noticias para el blog de Entre Interiores.

Ya NO descarga feeds: lee de la tabla `news_items`, que alimenta el agregador
unificado (`scripts.news.aggregate`). De ahí toma las noticias con `policy`
apta para el blog (`blog+ig`), las reescribe con voz editorial propia y crea
propuestas en el banco (`content_proposals`, kind='news').

El reparto de fuentes lo decide `data/news_sources.yaml`: la prensa comercial
vetada por la línea editorial (Mondo Sonoro, Efe Eme) y Reddit quedan como
`ig-only` y este consumidor nunca las toca.

Workflow:
    cron lunes 09:00 → lee news_items sin consumir (policy blog+ig) →
    por noticia: match de términos + rewrite editorial + imagen Wikimedia →
    inserta ContentProposal(kind='news') y marca la noticia como consumida →
    el admin la programa desde /biblioteca/admin/calendario.

Uso:
    python -m scripts.blog.scrape_news
    python -m scripts.blog.scrape_news --dry-run
    python -m scripts.blog.scrape_news --limit 10
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import yaml
from sqlalchemy import select

from app.db.models import ContentProposal, NewsItem
from app.db.session import SessionLocal
from app.services.article_extract import fetch_article_text
from app.services.content_dedup import (
    NEWS_RECENCY_DAYS,
    content_key_for,
    is_duplicate,
)
from app.services.news_research import research_and_write
from app.services.wikimedia import search_image

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SOURCES_PATH = Path("/app/data/news_sources.yaml")
DEFAULT_LIMIT = 25

HARD_REJECT_TERMS = {"clickbait"}


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _slugify(text: str, max_len: int = 100) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    ascii_only = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return ascii_only[:max_len]


def _flatten_terms(terms_groups: dict) -> list[str]:
    out: list[str] = []
    for _group, terms in (terms_groups or {}).items():
        for term in terms or []:
            t = term.strip().lower()
            if t:
                out.append(t)
    return out


def _match_term(blob_lower: str, terms: list[str]) -> str | None:
    for t in HARD_REJECT_TERMS:
        if t in blob_lower:
            return None
    for term in terms:
        if term in blob_lower:
            return term
    return None


_STOP = {
    "de", "la", "el", "en", "y", "a", "los", "las", "del", "un", "una", "por",
    "con", "su", "sus", "para", "que", "se", "al", "lo", "como", "más", "este",
}


def _title_tokens(title: str) -> set[str]:
    s = unicodedata.normalize("NFKD", (title or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    toks = re.findall(r"[a-z0-9]{3,}", s)
    return {t for t in toks if t not in _STOP}


def _title_overlap(a: str, b: str) -> float:
    """Jaccard de tokens significativos entre dos titulares (0..1)."""
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# --------------------------------------------------------------------------- #
# Admin notify
# --------------------------------------------------------------------------- #
def _notify_admin(summary: dict) -> None:
    """Resumen al admin: cuántas propuestas nuevas, descartes, errores."""
    body_lines = [
        f"Consumidor blog · {summary['ts']}",
        "",
        f"Noticias revisadas:        {summary['reviewed']}",
        f"Propuestas nuevas al banco: {summary['proposed']}",
        f"Descartadas (sin match):   {summary['no_match']}",
        f"Descartadas por el LLM:    {summary['rejected']}",
        f"Errores:                   {summary['errors']}",
        "",
    ]
    if summary["headlines"]:
        body_lines.append("Titulares procesados:")
        for h in summary["headlines"]:
            body_lines.append(f"  · [{h['action']}] {h['title']} ({h['source']})")
    text = "\n".join(body_lines)

    admin_email = os.getenv("ADMIN_EMAIL")
    if admin_email:
        from app.services.email import EmailError, send_email
        site_url = os.getenv("SITE_URL", "https://entreinteriores.com").rstrip("/")
        try:
            send_email(
                to=admin_email,
                subject=f"📰 Consumidor blog · {summary['proposed']} propuestas nuevas",
                html=f"<pre style='font-family:monospace'>{text}\n\n"
                f"<a href='{site_url}/biblioteca/admin/calendario'>Calendario</a></pre>",
                text=text,
            )
            return
        except EmailError as e:
            logger.warning("Admin email failed: %s", e)

    logger.info("Resumen admin:\n%s", text)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Máximo de noticias a procesar por run (def. {DEFAULT_LIMIT}).",
    )
    parser.add_argument(
        "--no-rewrite",
        action="store_true",
        help="No llama al LLM para reescribir (rápido, sin tokens).",
    )
    parser.add_argument(
        "--no-image",
        action="store_true",
        help="Salta búsqueda Wikimedia.",
    )
    args = parser.parse_args()

    if not SOURCES_PATH.exists():
        logger.error("No se encuentra %s", SOURCES_PATH)
        return

    with SOURCES_PATH.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    terms = _flatten_terms(cfg.get("terms_groups") or {})
    if not terms:
        logger.error("No hay términos definidos en news_sources.yaml")
        return
    logger.info("Términos activos: %d", len(terms))

    summary = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "reviewed": 0,
        "proposed": 0,
        "no_match": 0,
        "rejected": 0,
        "errors": 0,
        "headlines": [],
    }

    with SessionLocal() as db:
        # Noticias aptas para el blog que aún no se han convertido en propuesta,
        # las más relevantes primero.
        pending = db.execute(
            select(NewsItem)
            .where(
                NewsItem.policy == "blog+ig",
                NewsItem.consumed_blog.is_(False),
            )
            .order_by(NewsItem.relevance_score.desc())
            .limit(args.limit)
        ).scalars().all()
        logger.info("Noticias pendientes para el blog: %d", len(pending))

        used_in_run: set[int] = set()
        for news in pending:
            if news.id in used_in_run:
                continue  # ya consumida como fuente secundaria de otro post
            summary["reviewed"] += 1
            source_label = news.source_medium or news.source_name

            blob = f"{news.title} {news.summary or ''}".lower()
            term = _match_term(blob, terms)
            if not term:
                summary["no_match"] += 1
                if not args.dry_run:
                    news.consumed_blog = True
                    db.commit()
                continue

            # Dedup: si ya hay una propuesta con esa misma URL, no repetir.
            existing = db.execute(
                select(ContentProposal.id).where(
                    ContentProposal.source_url == news.url
                )
            ).scalar_one_or_none()
            if existing is not None:
                if not args.dry_run:
                    news.consumed_blog = True
                    db.commit()
                continue

            # Dedup por EVENTO (otra fuente / otra semana con el mismo tema):
            # si ya hay propuesta viva o post reciente del mismo evento, saltar.
            ckey = content_key_for("news", title=news.title)
            if is_duplicate(db, ckey, recency_days=NEWS_RECENCY_DAYS):
                summary["duplicate"] = summary.get("duplicate", 0) + 1
                if not args.dry_run:
                    news.consumed_blog = True
                    db.commit()
                continue

            # Reescritura editorial — el LLM provee slug, keywords de imagen y
            # entities para enriquecer schema.org `mentions`.
            image_keywords: list[str] = []
            entities: list[dict] = []
            related: list[NewsItem] = []
            if args.no_rewrite:
                title = news.title[:240]
                excerpt = (news.summary or "")[:200]
                body_md = (
                    f"{news.summary or ''}\n\n"
                    f"*Vía [{source_label}]({news.url}).*\n"
                )
                meta_title = title[:60]
                meta_description = excerpt[:155]
            else:
                # B1: cuerpo COMPLETO de la fuente principal (efímero, solo
                # como contexto para el LLM; no se persiste el original).
                primary = fetch_article_text(news.url) or news.summary or news.title
                # B3: otras noticias pendientes del MISMO evento (mismo término
                # + titular solapado) para cruzar fuentes en un solo post más
                # completo. Se marcarán consumidas para no duplicar.
                related = [
                    n for n in pending
                    if n.id != news.id and n.id not in used_in_run
                    and not n.consumed_blog
                    and _match_term(f"{n.title} {n.summary or ''}".lower(), terms) == term
                    and _title_overlap(news.title, n.title) >= 0.4
                ][:3]
                parts = [f"FUENTE PRINCIPAL ({source_label}):\n{primary}"]
                for r in related:
                    rbody = fetch_article_text(r.url) or r.summary or ""
                    if rbody:
                        parts.append(
                            "OTRA FUENTE DEL MISMO EVENTO "
                            f"({r.source_medium or r.source_name}):\n{rbody}"
                        )
                combined_excerpt = "\n\n====\n\n".join(parts)
                if related:
                    logger.info("  cruzando %d fuentes del mismo evento", len(parts))
                try:
                    # Proceso con investigación adaptativa del tema (web+corpus),
                    # vídeo y foto reales, y verificación factual. NO acredita al
                    # medio. Ver app.services.news_research.
                    rewritten = research_and_write(
                        db=db,
                        headline=news.title,
                        source_excerpt=combined_excerpt,
                        matched_term=term,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error("Investigación/escritura falló para %r: %s", news.title, exc)
                    summary["errors"] += 1
                    continue
                if not rewritten.get("is_relevant", True) or not rewritten.get("title"):
                    logger.info("Falso positivo descartado por LLM: %r", news.title)
                    summary["rejected"] += 1
                    if not args.dry_run:
                        news.consumed_blog = True
                        db.commit()
                    continue
                title = rewritten["title"][:240]
                excerpt = rewritten["excerpt"][:200]
                body_md = rewritten["body_md"]
                meta_title = rewritten["meta_title"][:60]
                meta_description = rewritten["meta_description"][:155]
                raw_kws = rewritten.get("image_keywords") or []
                if isinstance(raw_kws, list):
                    image_keywords = [
                        str(k).strip()
                        for k in raw_kws
                        if isinstance(k, str) and k.strip()
                    ][:5]
                raw_ents = rewritten.get("entities") or []
                if isinstance(raw_ents, list):
                    entities = [
                        e for e in raw_ents
                        if isinstance(e, dict) and e.get("name")
                    ]

            # Foto REAL del protagonista que devolvió la investigación (web).
            # Se sube a Cloudinary para servirla optimizada y por host permitido.
            hero = None
            img_url = rewritten.get("image_url") if not args.no_image else None
            if img_url:
                try:
                    from app.services.instagram import cloudinary_upload
                    hero = cloudinary_upload.upload(img_url, folder="entreinteriores-art")
                    logger.info("Foto del sujeto: %s", hero)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("subida de foto falló: %s", exc)
            else:
                logger.info("Sin foto del sujeto — post sin foto")

            if args.dry_run:
                summary["headlines"].append({
                    "action": "dry-run",
                    "title": title,
                    "source": source_label,
                })
                continue

            # Las noticias entran al BANCO de propuestas (content_proposals)
            # con kind='news' y el body ya reescrito. El admin las programa
            # desde la pestaña de calendario.
            proposal = ContentProposal(
                kind="news",
                title=title,
                angle="Noticia de actualidad",
                body_md=body_md,
                excerpt=excerpt,
                meta_title=meta_title,
                meta_description=meta_description,
                # Sin acreditar al medio: la investigación es nuestra. Se guarda
                # source_url para referencia interna, pero source_name=None evita
                # que la ficha muestre "Fuente: <medio>".
                source_url=news.url,
                source_name=None,
                hero_image_url=hero,
                hero_image_attribution=None,
                hero_image_license=None,
                hero_image_source_url=None,
                entities=entities,
                content_key=ckey,
                status="proposed",
            )
            db.add(proposal)
            news.consumed_blog = True
            for r in related:  # fuentes secundarias del mismo evento
                r.consumed_blog = True
                used_in_run.add(r.id)
            db.commit()
            summary["proposed"] += 1
            summary["headlines"].append({
                "action": "proposed",
                "title": title,
                "source": source_label,
            })

    logger.info(
        "Run terminado: %d propuestas nuevas de %d noticias revisadas · %d errores",
        summary["proposed"], summary["reviewed"], summary["errors"],
    )
    if args.dry_run:
        for h in summary["headlines"]:
            print(f"  [{h['action']}] {h['title']} ({h['source']})")
    else:
        _notify_admin(summary)


if __name__ == "__main__":
    main()
