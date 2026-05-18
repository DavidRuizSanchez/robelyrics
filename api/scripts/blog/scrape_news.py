"""Scraper semanal de noticias sobre Robe / Extremoduro.

Workflow:
  1. Recorre `sources/news_whitelist.yaml` (fuentes permitidas).
  2. Para cada fuente, obtiene los items recientes (RSS o HTML).
  3. Filtra por términos relevantes (configurable en el YAML).
  4. Inserta en `posts` con status='pending_review' (deduplicado por
     source_url). Los items previos no se reescriben.
  5. Si NOTIFY_ADMIN_TOKEN está configurado, manda resumen a Telegram al
     admin con la lista de candidatos a revisar.

El admin revisa en panel admin y aprueba/rechaza manualmente. NUNCA publica
de forma automática — la aprobación es obligatoria.

Pensado para correr semanalmente vía cron:
    0 9 * * 1 cd /opt/robelyrics && docker compose exec -T api python -m scripts.blog.scrape_news

NOTA: este es el esqueleto base. La whitelist de fuentes y el parser por
fuente se afinan en `sources/news_whitelist.yaml` y `_fetch_<source>` según
qué portales se quieran cubrir. Los parsers de RSS están listos; para
fuentes solo-HTML hay que añadir selectores CSS por fuente.
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
from sqlalchemy import select

from app.db.models import Post
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

WHITELIST_PATH = Path("/app/data/news_whitelist.yaml")
USER_AGENT = "Mozilla/5.0 RobeLyrics-NewsBot/1.0 (+https://entreinteriores.com/blog)"
HTTP_TIMEOUT = 20.0

# Palabras prohibidas en cualquier fuente — si alguna aparece, descartamos el
# item (suelen ser etiquetas de prensa veta da en el corpus principal).
HARD_REJECT_TERMS = {"clickbait"}


def slugify(text: str, max_len: int = 100) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    ascii_only = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return ascii_only[:max_len]


def fetch_rss(url: str) -> Iterator[dict]:
    """Parse RSS/Atom genérico. Devuelve {title, link, summary, published_at}."""
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT}) as c:
            r = c.get(url)
            r.raise_for_status()
            root = ET.fromstring(r.text)
    except Exception as e:
        logger.warning("fetch_rss failed for %s: %s", url, e)
        return

    # Soporta RSS 2.0 (`channel/item`) y Atom (`entry`)
    ns_atom = "{http://www.w3.org/2005/Atom}"

    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        summary = (item.findtext("description") or "").strip()
        pub = item.findtext("pubDate") or ""
        yield {"title": title, "link": link, "summary": summary, "published_at_raw": pub}

    for entry in root.iter(f"{ns_atom}entry"):
        title = (entry.findtext(f"{ns_atom}title") or "").strip()
        link_el = entry.find(f"{ns_atom}link")
        link = link_el.get("href") if link_el is not None else ""
        summary = (entry.findtext(f"{ns_atom}summary") or "").strip()
        pub = entry.findtext(f"{ns_atom}published") or ""
        yield {"title": title, "link": link, "summary": summary, "published_at_raw": pub}


def matches_terms(text: str, terms: list[str]) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    if any(term in text_lower for term in HARD_REJECT_TERMS):
        return False
    return any(term in text_lower for term in terms)


def _render_admin_email(candidates: list[dict], admin_url: str) -> tuple[str, str]:
    """Email para el admin con la lista de candidatos a revisar."""
    items_html = ""
    items_text: list[str] = []
    for c in candidates:
        items_html += f"""\
<li style="margin:0 0 12px;padding:12px 14px;background:rgba(237,228,211,0.03);border-left:3px solid #e85050;">
  <p style="font-family:Georgia,serif;font-size:15px;color:#ede4d3;margin:0 0 4px;line-height:1.35;">
    <strong>{c['title']}</strong>
  </p>
  <p style="font-family:'Courier New',monospace;font-size:11px;color:rgba(237,228,211,0.5);margin:0 0 4px;">
    {c['source_name']} ·
    <a href="{c['source_url']}" style="color:#e85050;text-decoration:none;">fuente original ↗</a>
  </p>
  {f'<p style="font-family:Georgia,serif;font-style:italic;font-size:13px;color:rgba(237,228,211,0.7);margin:6px 0 0;line-height:1.5;">{c["excerpt"]}</p>' if c.get("excerpt") else ""}
</li>"""
        items_text.append(f"· {c['title']}\n  {c['source_name']} — {c['source_url']}")

    html = f"""\
<!doctype html>
<html lang="es"><body style="margin:0;padding:32px;background:#0d0b0a;color:#ede4d3;font-family:Georgia,serif;">
  <div style="max-width:620px;margin:0 auto;padding:32px;border:1px solid rgba(237,228,211,0.08);background:rgba(237,228,211,0.02);">
    <p style="font-family:'Courier New',monospace;font-size:10px;letter-spacing:3px;text-transform:uppercase;color:#e85050;margin:0 0 8px;">
      entre interiores · admin
    </p>
    <h1 style="font-family:Georgia,serif;font-size:24px;color:#ede4d3;margin:0 0 8px;">
      {len(candidates)} candidato{'s' if len(candidates) != 1 else ''} de noticia para revisar
    </h1>
    <p style="font-style:italic;line-height:1.6;color:rgba(237,228,211,0.6);font-size:14px;margin:0 0 24px;">
      El scraper semanal ha encontrado lo siguiente. Revísalo y publica/rechaza
      desde el panel admin. Solo lo que apruebes se envía a los suscriptores.
    </p>
    <ul style="list-style:none;padding:0;margin:0 0 24px;">
      {items_html}
    </ul>
    <p style="margin:24px 0 0;text-align:center;">
      <a href="{admin_url}" style="display:inline-block;padding:14px 28px;border:1px solid #e85050;color:#e85050;text-decoration:none;font-family:'Courier New',monospace;font-size:11px;letter-spacing:3px;text-transform:uppercase;">
        revisar en el panel
      </a>
    </p>
  </div>
</body></html>"""
    text = (
        f"{len(candidates)} candidatos de noticia para revisar:\n\n"
        + "\n\n".join(items_text)
        + f"\n\nRevisar en el panel: {admin_url}\n"
    )
    return html, text


def maybe_notify_admin(candidates: list[dict]) -> None:
    """Notifica al admin con la lista de candidatos. Prefiere email
    (ADMIN_EMAIL + SMTP/Resend configurado); cae a Telegram si está
    configurado; si nada, solo log."""
    if not candidates:
        return

    summary_lines = [f"📰 {len(candidates)} candidato(s) para revisar:"]
    for c in candidates[:15]:
        summary_lines.append(f"  · {c['title']} — {c['source_name']}")
    summary = "\n".join(summary_lines)

    # 1) Email al admin (preferido).
    admin_email = os.getenv("ADMIN_EMAIL")
    if admin_email:
        from app.services.email import send_email, EmailError
        site_url = os.getenv("SITE_URL", "https://entreinteriores.com").rstrip("/")
        admin_url = f"{site_url}/biblioteca/admin/posts"
        try:
            html, text = _render_admin_email(candidates, admin_url)
            send_email(
                to=admin_email,
                subject=f"📰 {len(candidates)} noticia(s) para revisar · Entre Interiores",
                html=html,
                text=text,
            )
            logger.info("Admin email enviado a %s", admin_email)
            return
        except EmailError as e:
            logger.warning("Admin email failed: %s — fallback a log/Telegram", e)

    # 2) Telegram fallback.
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_ADMIN_CHAT_ID")
    if token and chat_id:
        try:
            with httpx.Client(timeout=10.0) as c:
                c.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": summary},
                )
            return
        except Exception as e:
            logger.warning("Telegram notify failed: %s", e)

    # 3) Solo log.
    logger.info("Admin notification skipped (sin ADMIN_EMAIL ni TELEGRAM).\n%s", summary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="No inserta, solo lista.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not WHITELIST_PATH.exists():
        logger.error("No existe %s. Crea la whitelist primero.", WHITELIST_PATH)
        return

    with WHITELIST_PATH.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    terms = [t.lower() for t in (cfg.get("terms") or [])]
    sources = cfg.get("sources") or []

    candidates: list[dict] = []

    for src in sources:
        if not src.get("enabled", True):
            continue
        kind = src.get("kind", "rss")
        name = src["name"]
        url = src["url"]
        logger.info("Fetch %s (%s)", name, url)

        if kind == "rss":
            for item in fetch_rss(url):
                if not item["title"] or not item["link"]:
                    continue
                blob = f"{item['title']} {item['summary']}"
                if not matches_terms(blob, terms):
                    continue
                candidates.append({
                    "source_name": name,
                    "source_url": item["link"],
                    "title": item["title"],
                    "excerpt": item["summary"][:400] if item["summary"] else None,
                })
        else:
            logger.warning("Source kind '%s' no implementado todavía (%s).", kind, name)

    logger.info("Total candidatos: %d", len(candidates))
    if args.dry_run:
        for c in candidates:
            print(f"  - [{c['source_name']}] {c['title']}")
        return

    added = 0
    with SessionLocal() as db:
        for c in candidates:
            existing = db.execute(
                select(Post).where(Post.source_url == c["source_url"])
            ).scalar_one_or_none()
            if existing:
                continue
            slug = slugify(c["title"])
            # Garantizar unicidad de slug (collisions raras)
            base = slug
            i = 2
            while db.execute(select(Post).where(Post.slug == slug)).scalar_one_or_none():
                slug = f"{base}-{i}"
                i += 1
            body = (
                f"_Resumen automático de la fuente original — el editor revisará "
                f"y reescribirá antes de publicar._\n\n"
                f"{c.get('excerpt') or ''}\n\n"
                f"Fuente original: {c['source_url']}"
            )
            post = Post(
                slug=slug,
                kind="news",
                status="pending_review",
                title=c["title"][:240],
                excerpt=c.get("excerpt"),
                body_md=body,
                source_url=c["source_url"],
                source_name=c["source_name"],
            )
            db.add(post)
            added += 1
        db.commit()

    logger.info("Insertados como pending_review: %d", added)
    maybe_notify_admin(candidates)


if __name__ == "__main__":
    main()
