"""Descarga posts de blogs fan listados en data/sources.yaml sección `blogs`.

Estrategia:
  1. Para cada blog, intenta el feed RSS estándar (WordPress: /feed/, Blogspot: /feeds/posts/default).
  2. Si el feed devuelve algo, parsea entradas → autor, fecha, contenido.
  3. Si no hay feed, scraping HTML genérico: descarga la URL y extrae <article> /
     bloques de párrafos largos.
  4. Filtros: contenido limpio ≥ 400 chars, pagebody que contenga al menos una
     de ["Robe", "Extremoduro", "Iniesta"] (case-insensitive con accents).

Sleep 2s entre requests por dominio. Respeta robots.txt vía httpx (mejor: no
lanzar requests en paralelo, solo seriales).

Ejecución: docker compose exec api python -m scripts.research.fetch_blogs
"""
from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from scripts.research.common import (
    clean_text,
    get_session,
    load_sources_yaml,
    log,
    normalize,
    polite_sleep,
    upsert_source,
)

USER_AGENT = "robelyrics-research/1.0 (personal use; contact davidruizsanchez@gmail.com)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/rss+xml,application/atom+xml,*/*"}
RELEVANT_TERMS = {"robe", "extremoduro", "iniesta"}
MIN_CONTENT_CHARS = 400


# --------------------------------------------------------------------------- #
# RSS / Atom
# --------------------------------------------------------------------------- #
def candidate_feed_urls(blog_url: str) -> list[str]:
    p = urlparse(blog_url)
    base = f"{p.scheme}://{p.netloc}"
    # Si la URL ya apunta a un post concreto, también probamos al root.
    return [
        urljoin(base, "/feed/"),  # WordPress
        urljoin(base, "/feed"),
        urljoin(base, "/rss"),
        urljoin(base, "/feeds/posts/default"),  # Blogspot
        urljoin(base, "/feeds/posts/default?alt=rss"),
        urljoin(base, "/atom.xml"),
    ]


def parse_feed(xml_text: str) -> list[dict[str, Any]]:
    """Devuelve [{title, link, author, published, content}, ...] independiente de RSS/Atom."""
    out: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    # Atom (Blogspot)
    ns_atom = "{http://www.w3.org/2005/Atom}"
    if root.tag.endswith("feed"):
        for entry in root.findall(f"{ns_atom}entry"):
            title = (entry.findtext(f"{ns_atom}title") or "").strip()
            link_el = entry.find(f"{ns_atom}link[@rel='alternate']") or entry.find(f"{ns_atom}link")
            link = link_el.get("href") if link_el is not None else ""
            author_el = entry.find(f"{ns_atom}author/{ns_atom}name")
            author = author_el.text if author_el is not None else None
            published = entry.findtext(f"{ns_atom}published") or entry.findtext(f"{ns_atom}updated")
            content_el = entry.find(f"{ns_atom}content") or entry.find(f"{ns_atom}summary")
            content = content_el.text if content_el is not None else ""
            out.append({"title": title, "link": link, "author": author, "published": published, "content": content})
        return out

    # RSS 2.0 (WordPress)
    if root.tag.endswith("rss") or root.tag == "rss":
        channel = root.find("channel")
        if channel is None:
            return []
        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            author = item.findtext("{http://purl.org/dc/elements/1.1/}creator") or item.findtext("author")
            published = item.findtext("pubDate")
            content = (
                item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
                or item.findtext("description")
                or ""
            )
            out.append({"title": title, "link": link, "author": author, "published": published, "content": content})
    return out


def parse_pubdate(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return parsedate_to_datetime(s)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# HTML genérico
# --------------------------------------------------------------------------- #
def extract_article_text(html_str: str) -> str:
    soup = BeautifulSoup(html_str, "html.parser")
    # Strip scripts, styles, nav, footer
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    # Buscar contenedor principal típico
    candidates = soup.select("article, .entry-content, .post-content, .post-body, main")
    if candidates:
        return candidates[0].get_text(" ", strip=True)
    return soup.get_text(" ", strip=True)


# --------------------------------------------------------------------------- #
# Filtros
# --------------------------------------------------------------------------- #
def is_relevant(text: str) -> bool:
    n = normalize(text)
    return any(term in n for term in RELEVANT_TERMS)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def fetch(client: httpx.Client, url: str) -> str | None:
    try:
        r = client.get(url, headers=HEADERS, follow_redirects=True)
        if r.status_code == 200:
            return r.text
        log(f"  {r.status_code} {url}", "warn")
        return None
    except httpx.HTTPError as e:
        log(f"  http error {url}: {e}", "warn")
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-per-blog", type=int, default=None)
    args = parser.parse_args()

    sources = load_sources_yaml()
    blogs = sources.get("blogs", []) or []
    if not blogs:
        log("Sin blogs en sources.yaml", "warn")
        return

    total_posts = 0

    with httpx.Client(timeout=20) as client, get_session() as db:
        for blog in blogs:
            blog_url = blog["url"]
            blog_name = blog["name"]
            log(f"blog · {blog_name}")

            # Intento RSS / Atom
            entries: list[dict[str, Any]] = []
            for feed_url in candidate_feed_urls(blog_url):
                xml_text = fetch(client, feed_url)
                polite_sleep(2.0)
                if xml_text and ("<rss" in xml_text or "<feed" in xml_text):
                    entries = parse_feed(xml_text)
                    if entries:
                        log(f"  feed OK · {len(entries)} entradas en {feed_url}")
                        break

            # Fallback: scraping de la URL del yaml
            if not entries:
                html_str = fetch(client, blog_url)
                polite_sleep(2.0)
                if html_str:
                    article_text = extract_article_text(html_str)
                    if len(article_text) >= MIN_CONTENT_CHARS and is_relevant(article_text):
                        upsert_source(
                            db,
                            kind="blog",
                            url=blog_url,
                            title=blog_name,
                            author=None,
                            content_raw=article_text,
                            content_clean=clean_text(article_text),
                            quality_score=0.5,
                        )
                        total_posts += 1
                continue

            count = 0
            for entry in entries:
                if args.limit_per_blog and count >= args.limit_per_blog:
                    break
                content = entry["content"] or ""
                # El content de RSS/Atom suele venir con HTML; lo strippeamos
                soup = BeautifulSoup(content, "html.parser")
                text = soup.get_text(" ", strip=True)
                if len(text) < MIN_CONTENT_CHARS or not is_relevant(text):
                    continue
                upsert_source(
                    db,
                    kind="blog",
                    url=entry["link"] or blog_url,
                    title=entry["title"],
                    author=entry.get("author"),
                    published_at=parse_pubdate(entry.get("published")),
                    content_raw=content,
                    content_clean=clean_text(text),
                    quality_score=0.6,
                )
                total_posts += 1
                count += 1

    log(f"blog posts upserted: {total_posts}", "ok")


if __name__ == "__main__":
    main()
