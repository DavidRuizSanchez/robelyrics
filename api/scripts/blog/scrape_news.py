"""Scraper semanal de noticias sobre Robe / Extremoduro y universo cercano.

Diferencias respecto a la versión MVP:
  - Lee `data/news_whitelist.yaml` con la estructura nueva (terms_groups +
    sources con tier).
  - Soporta HTML scraping además de RSS (selector CSS por fuente).
  - Reescribe cada noticia con voz editorial propia (content_generator.
    rewrite_news_editorial) — no copia texto de la fuente.
  - Busca imagen libre en Wikimedia para el hero.
  - Auto-publica con `publishing.schedule_or_publish` si la fuente es
    `tier: trusted`; en caso contrario inserta como `pending_review`.
  - Registra cada run en `news_source_runs` para observabilidad.

Workflow:
    cron lunes 09:00 UTC → 1) fetch fuentes 2) match terms 3) por candidato:
    rewrite + wikimedia + publish/queue 4) notify admin con resumen.

Uso:
    python -m scripts.blog.scrape_news
    python -m scripts.blog.scrape_news --dry-run
    python -m scripts.blog.scrape_news --source "Hoy (Extremadura) — Cultura"
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx
import yaml
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.db.models import NewsSourceRun, Post
from app.db.session import SessionLocal
from app.services.content_generator import rewrite_news_editorial
from app.services.publishing import schedule_or_publish
from app.services.wikimedia import search_image

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

WHITELIST_PATH = Path("/app/data/news_whitelist.yaml")
USER_AGENT = "Mozilla/5.0 RobeLyrics-NewsBot/1.0 (+https://entreinteriores.com/blog)"
HTTP_TIMEOUT = 20.0

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
    for group, terms in (terms_groups or {}).items():
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


# --------------------------------------------------------------------------- #
# Fetchers
# --------------------------------------------------------------------------- #
def fetch_rss(url: str) -> Iterator[dict]:
    try:
        with httpx.Client(
            timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}
        ) as c:
            r = c.get(url)
            r.raise_for_status()
            root = ET.fromstring(r.text)
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_rss failed for %s: %s", url, e)
        return

    ns_atom = "{http://www.w3.org/2005/Atom}"
    for item in root.iter("item"):
        yield {
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "summary": (item.findtext("description") or "").strip(),
        }
    for entry in root.iter(f"{ns_atom}entry"):
        link_el = entry.find(f"{ns_atom}link")
        yield {
            "title": (entry.findtext(f"{ns_atom}title") or "").strip(),
            "link": link_el.get("href") if link_el is not None else "",
            "summary": (entry.findtext(f"{ns_atom}summary") or "").strip(),
        }


def fetch_html(url: str, selector: str) -> Iterator[dict]:
    """Scrapea una página índice. `selector` es un selector CSS que apunta a
    cada item; dentro buscamos un `<a>` con título y href, y opcionalmente un
    bloque de excerpt (primer `<p>` o atributo `data-summary`)."""
    try:
        with httpx.Client(
            timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as c:
            r = c.get(url)
            r.raise_for_status()
            html = r.text
    except Exception as e:  # noqa: BLE001
        logger.warning("fetch_html failed for %s: %s", url, e)
        return

    soup = BeautifulSoup(html, "html.parser")
    base = urlparse(url)
    base_root = f"{base.scheme}://{base.netloc}"
    for el in soup.select(selector):
        a = el.find("a")
        if a is None:
            continue
        title = (a.get_text() or "").strip()
        href = a.get("href") or ""
        if href.startswith("/"):
            href = base_root + href
        if not title or not href:
            continue
        summary_el = el.find("p")
        summary = (summary_el.get_text() or "").strip() if summary_el else ""
        yield {"title": title, "link": href, "summary": summary}


# --------------------------------------------------------------------------- #
# Admin notify
# --------------------------------------------------------------------------- #
def _notify_admin(summary: dict) -> None:
    """Resumen al admin: cuántos auto-publicados, cuántos en pending, errores."""
    body_lines = [
        f"Scraper run · {summary['ts']}",
        "",
        f"Auto-publicados (trusted): {summary['published']}",
        f"Encolados (cap lleno):     {summary['scheduled']}",
        f"Pending review:            {summary['pending']}",
        f"Sin match:                 {summary['no_match']}",
        f"Errores fuentes:           {summary['errors']}",
        "",
    ]
    if summary["headlines"]:
        body_lines.append("Headlines procesados:")
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
                subject=f"📰 Scraper run · {summary['published']} pub / {summary['scheduled']} en cola",
                html=f"<pre style='font-family:monospace'>{text}\n\n"
                f"<a href='{site_url}/biblioteca/admin/posts'>Panel admin</a></pre>",
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
    parser.add_argument("--source", help="Limita a una fuente concreta por nombre")
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

    if not WHITELIST_PATH.exists():
        logger.error("Whitelist no encontrada en %s", WHITELIST_PATH)
        return

    with WHITELIST_PATH.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Compat retro: si todavía hay `terms` plana (legacy), la añadimos a un
    # grupo `legacy`. La nueva estructura es `terms_groups`.
    terms_groups = cfg.get("terms_groups")
    if not terms_groups and "terms" in cfg:
        terms_groups = {"legacy": cfg["terms"]}
    terms = _flatten_terms(terms_groups or {})
    if not terms:
        logger.error("No hay términos definidos en la whitelist")
        return
    logger.info("Términos activos: %d (de %d grupos)", len(terms), len(terms_groups or {}))

    sources = cfg.get("sources") or []
    if args.source:
        sources = [s for s in sources if s.get("name") == args.source]

    summary = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "published": 0,
        "scheduled": 0,
        "pending": 0,
        "no_match": 0,
        "errors": 0,
        "headlines": [],
    }

    with SessionLocal() as db:
        for src in sources:
            if not src.get("enabled", True):
                continue
            name = src["name"]
            url = src["url"]
            kind = src.get("kind", "rss")
            tier = src.get("tier", "review")

            logger.info("Fetch %s (%s, tier=%s)", name, url, tier)
            run = NewsSourceRun(source_name=name)
            db.add(run)
            db.commit()
            db.refresh(run)

            items: list[dict] = []
            try:
                if kind == "rss":
                    items = list(fetch_rss(url))
                elif kind == "html":
                    selector = src.get("selector")
                    if not selector:
                        raise ValueError("kind=html requiere `selector`")
                    items = list(fetch_html(url, selector))
                else:
                    raise ValueError(f"kind '{kind}' desconocido")
            except Exception as exc:  # noqa: BLE001
                logger.error("Source %s falló: %s", name, exc)
                run.error = str(exc)[:1000]
                run.finished_at = datetime.now(timezone.utc)
                db.commit()
                summary["errors"] += 1
                continue

            run.items_found = len(items)

            for item in items:
                if not item["title"] or not item["link"]:
                    continue
                blob = f"{item['title']} {item['summary']}".lower()
                term = _match_term(blob, terms)
                if not term:
                    continue

                # Dedup por source_url
                existing = db.execute(
                    select(Post).where(Post.source_url == item["link"])
                ).scalar_one_or_none()
                if existing is not None:
                    continue

                slug = _slugify(item["title"])
                base = slug
                i = 2
                while db.execute(
                    select(Post).where(Post.slug == slug)
                ).scalar_one_or_none():
                    slug = f"{base}-{i}"
                    i += 1

                # Reescritura editorial
                if args.no_rewrite:
                    title = item["title"][:240]
                    excerpt = (item["summary"] or "")[:200]
                    body_md = (
                        f"{item['summary'] or ''}\n\n"
                        f"*Vía [{name}]({item['link']}).*\n"
                    )
                    meta_title = title[:60]
                    meta_description = excerpt[:155]
                else:
                    rewritten = rewrite_news_editorial(
                        headline=item["title"],
                        source_excerpt=item["summary"] or item["title"],
                        source_url=item["link"],
                        source_name=name,
                        matched_term=term,
                    )
                    # Si el LLM devolvió title vacío → falso positivo, skip
                    if not rewritten.get("title"):
                        logger.info(
                            "Falso positivo descartado por LLM: %r", item["title"]
                        )
                        continue
                    title = rewritten["title"][:240]
                    excerpt = rewritten["excerpt"][:200]
                    body_md = rewritten["body_md"]
                    meta_title = rewritten["meta_title"][:60]
                    meta_description = rewritten["meta_description"][:155]

                # Imagen Wikimedia
                img = None
                if not args.no_image:
                    img = search_image(term)
                if img is None and not args.no_image:
                    img = search_image("Extremoduro")
                hero_url = img.thumb_url if img else None
                if img:
                    body_md = body_md.rstrip() + "\n\n" + img.attribution_text + "\n"

                run.items_inserted += 1

                action_label = "pending"
                if args.dry_run:
                    summary["headlines"].append({
                        "action": "dry-run",
                        "title": title,
                        "source": name,
                    })
                    continue

                post = Post(
                    slug=slug,
                    kind="news",
                    status="pending_review" if tier != "trusted" else "draft",
                    title=title,
                    excerpt=excerpt,
                    body_md=body_md,
                    meta_title=meta_title,
                    meta_description=meta_description,
                    source_url=item["link"],
                    source_name=name,
                    hero_image_url=hero_url,
                    hero_image_attribution=img.attribution_text if img else None,
                    hero_image_license=img.license_short if img else None,
                    hero_image_source_url=img.source_page_url if img else None,
                )
                db.add(post)
                db.commit()
                db.refresh(post)

                if tier == "trusted":
                    result = schedule_or_publish(db, post)
                    if result["action"] == "published":
                        summary["published"] += 1
                        run.items_published += 1
                        action_label = "published"
                    else:
                        summary["scheduled"] += 1
                        run.items_scheduled += 1
                        action_label = "scheduled"
                else:
                    summary["pending"] += 1
                    action_label = "pending"

                summary["headlines"].append({
                    "action": action_label,
                    "title": title,
                    "source": name,
                })

            run.finished_at = datetime.now(timezone.utc)
            db.commit()

    summary["no_match"] = 0  # se calcularía si quisiéramos detallarlo
    logger.info(
        "Run terminado: %d pub / %d enc / %d pending / %d errors",
        summary["published"], summary["scheduled"], summary["pending"], summary["errors"],
    )
    if not args.dry_run:
        _notify_admin(summary)
    else:
        for h in summary["headlines"]:
            print(f"  [{h['action']}] {h['title']} ({h['source']})")


if __name__ == "__main__":
    main()
