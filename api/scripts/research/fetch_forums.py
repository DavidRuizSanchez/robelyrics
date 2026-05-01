"""Scraper genérico de foros listados en data/sources.yaml sección `forums`.

Cada foro tiene su propia estructura HTML, así que usamos un extractor que
recorre selectores comunes (phpBB, vBulletin, Mediavida, etc.) y se queda
con bloques de texto largos. Es voluntariamente conservador: prefiere
perder algún post a colar ruido.

Este scraper procesa solo las URLs CONCRETAS que están en sources.yaml
(no rastrea el foro entero). El curado humano del yaml es lo que filtra.

Ejecución: docker compose exec api python -m scripts.research.fetch_forums
"""
from __future__ import annotations

import argparse
import re

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
HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,*/*"}
MIN_POST_CHARS = 200
RELEVANT_TERMS = {"robe", "extremoduro", "iniesta"}

# Selectores de "post" por dominio. Estos los he derivado inspeccionando
# las estructuras típicas; son aproximaciones razonables, no perfectas.
POST_SELECTORS = {
    "mediavida.com": ["div.msg-body", ".msg-content", "div.post"],
    "foroazkenarock.com": ["div.postbody", "div.content"],  # phpBB
    "foro.nochederock.com": ["div.postbody", "div.content"],
    # Genérico phpBB
    "_default": ["div.postbody", "div.post-body", "article", ".message-body", ".bbWrapper", "div.content"],
}


def selectors_for(url: str) -> list[str]:
    for domain, sels in POST_SELECTORS.items():
        if domain != "_default" and domain in url:
            return sels
    return POST_SELECTORS["_default"]


def is_relevant(text: str) -> bool:
    n = normalize(text)
    return any(term in n for term in RELEVANT_TERMS)


def extract_posts(html_str: str, url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html_str, "html.parser")
    # Limpiar
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "blockquote"]):
        tag.decompose()

    posts: list[dict[str, str]] = []
    for sel in selectors_for(url):
        for el in soup.select(sel):
            text = el.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) >= MIN_POST_CHARS:
                posts.append({"text": text})
        if posts:
            break  # primer selector que encuentra algo, paramos

    # Fallback: si los selectores no encuentran nada, todos los <p> grandes
    if not posts:
        for p in soup.find_all("p"):
            text = p.get_text(" ", strip=True)
            if len(text) >= MIN_POST_CHARS:
                posts.append({"text": text})

    # Dedupe por texto exacto
    seen = set()
    deduped = []
    for p in posts:
        key = p["text"][:200]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)
    return deduped


def fetch(client: httpx.Client, url: str) -> str | None:
    try:
        r = client.get(url, headers=HEADERS, follow_redirects=True)
        if r.status_code != 200:
            log(f"  {r.status_code} {url}", "warn")
            return None
        return r.text
    except httpx.HTTPError as e:
        log(f"  error {url}: {e}", "warn")
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-posts-per-thread", type=int, default=200)
    args = parser.parse_args()

    sources = load_sources_yaml()
    forums = sources.get("forums", []) or []
    forums = [f for f in forums if f.get("status") == "active"]
    if not forums:
        log("Sin foros activos en sources.yaml", "warn")
        return

    total_posts = 0

    with httpx.Client(timeout=20) as client, get_session() as db:
        for forum in forums:
            url = forum["url"]
            name = forum["name"]
            log(f"forum · {name}")

            html_str = fetch(client, url)
            polite_sleep(3.0)
            if not html_str:
                continue

            posts = extract_posts(html_str, url)
            log(f"  {len(posts)} posts candidatos")

            count = 0
            for i, p in enumerate(posts):
                if count >= args.max_posts_per_thread:
                    break
                if not is_relevant(p["text"]):
                    continue
                upsert_source(
                    db,
                    kind="forum",
                    # url única por post: ancla con índice
                    url=f"{url}#post-{i}",
                    title=name,
                    author=None,
                    content_raw=p["text"],
                    content_clean=clean_text(p["text"]),
                    quality_score=0.5,
                )
                total_posts += 1
                count += 1

            log(f"  guardados: {count}")

    log(f"forum posts upserted: {total_posts}", "ok")


if __name__ == "__main__":
    main()
