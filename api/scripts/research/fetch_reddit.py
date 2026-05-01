"""Descarga posts y comentarios largos de Reddit relacionados con Robe/Extremoduro.

Modos:
  - Si REDDIT_CLIENT_ID está configurado → usa PRAW (auth, mejor rate).
  - Si vacío → endpoint JSON público de Reddit (sin auth, rate ~30 req/min).

El plan B es suficiente para nuestro caso: r/Extremoduro y r/Robe parecen
tener poca masa crítica, y Reddit-wide search devuelve los hilos
relevantes igual sin auth.

Filtros de calidad:
  - posts: score ≥ 5, body ≥ 200 chars (descarta los que solo enlazan a YT/Spotify)
  - comments: score ≥ 5, body ≥ 200 chars

Ejecución: docker compose exec api python -m scripts.research.fetch_reddit
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

from app.config import get_settings
from scripts.research.common import (
    clean_text,
    get_session,
    log,
    polite_sleep,
    upsert_source,
)

REDDIT_HEADERS = {
    "User-Agent": "robelyrics-research/1.0 (by u/davidruizsanchez)",
    "Accept": "application/json",
}

QUERIES = [
    {"sub": "Extremoduro", "kind": "subreddit"},
    {"sub": "Robe", "kind": "subreddit"},
    {"q": "Extremoduro letras significado", "kind": "search"},
    {"q": "Robe Iniesta análisis", "kind": "search"},
    {"q": "La ley innata significado", "kind": "search"},
]

MIN_BODY_CHARS = 200
MIN_SCORE = 5


# --------------------------------------------------------------------------- #
# Modo 1: PRAW (con auth)
# --------------------------------------------------------------------------- #
def run_with_praw() -> tuple[int, int]:
    import praw

    settings = get_settings()
    reddit = praw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent or REDDIT_HEADERS["User-Agent"],
    )
    reddit.read_only = True

    posts_in = 0
    comments_in = 0

    with get_session() as db:
        for q in QUERIES:
            log(f"reddit/PRAW · {q}")
            try:
                if q["kind"] == "subreddit":
                    submissions = reddit.subreddit(q["sub"]).top(time_filter="all", limit=100)
                else:
                    submissions = reddit.subreddit("all").search(q["q"], sort="top", limit=50)
                for sub in submissions:
                    posts_in += _ingest_submission(db, sub, comments_in_counter=lambda n: None)
            except Exception as e:  # noqa: BLE001
                log(f"  PRAW falló: {type(e).__name__}: {e}", "warn")
                continue
            polite_sleep(1.0)
    return posts_in, comments_in


def _ingest_submission(db, sub, *, comments_in_counter) -> int:
    """Para PRAW. Devuelve 1 si insertó el post."""
    body = sub.selftext or ""
    if len(body) < MIN_BODY_CHARS or sub.score < MIN_SCORE:
        return 0
    upsert_source(
        db,
        kind="reddit",
        url=f"https://www.reddit.com{sub.permalink}",
        title=sub.title,
        author=str(sub.author) if sub.author else None,
        published_at=datetime.fromtimestamp(sub.created_utc, tz=timezone.utc),
        content_raw=body,
        content_clean=clean_text(body),
        quality_score=min(1.0, sub.score / 100),
    )
    return 1


# --------------------------------------------------------------------------- #
# Modo 2: JSON público (sin auth)
# --------------------------------------------------------------------------- #
def fetch_json(client: httpx.Client, url: str) -> dict[str, Any] | None:
    r = client.get(url, headers=REDDIT_HEADERS)
    if r.status_code == 403:
        log(f"  403 (subreddit privado o bloqueado): {url}", "warn")
        return None
    if r.status_code == 404:
        log(f"  404 (no existe): {url}", "warn")
        return None
    if r.status_code == 429:
        log(f"  429 rate-limit, sleeping 30s", "warn")
        polite_sleep(30)
        return None
    try:
        r.raise_for_status()
    except httpx.HTTPError as e:
        log(f"  http error {e}", "warn")
        return None
    return r.json()


def iter_listing(data: dict[str, Any]) -> Iterable[dict[str, Any]]:
    children = (data or {}).get("data", {}).get("children", []) or []
    for c in children:
        kind = c.get("kind")
        d = c.get("data") or {}
        if kind == "t3":  # post
            yield {"kind": "post", **d}
        elif kind == "t1":  # comment
            yield {"kind": "comment", **d}


def run_public() -> tuple[int, int]:
    posts_in = 0
    comments_in = 0

    with httpx.Client(timeout=20) as client, get_session() as db:
        for q in QUERIES:
            if q["kind"] == "subreddit":
                url = f"https://www.reddit.com/r/{q['sub']}/top.json?t=all&limit=100"
            else:
                from urllib.parse import quote_plus
                url = f"https://www.reddit.com/search.json?q={quote_plus(q['q'])}&sort=top&t=all&limit=50"

            log(f"reddit/JSON · {q}")
            data = fetch_json(client, url)
            if not data:
                polite_sleep(2.0)
                continue

            for it in iter_listing(data):
                body = it.get("selftext") or ""
                score = it.get("score") or 0
                if len(body) < MIN_BODY_CHARS or score < MIN_SCORE:
                    continue
                upsert_source(
                    db,
                    kind="reddit",
                    url=f"https://www.reddit.com{it.get('permalink', '')}",
                    title=it.get("title"),
                    author=it.get("author"),
                    published_at=datetime.fromtimestamp(it["created_utc"], tz=timezone.utc) if it.get("created_utc") else None,
                    content_raw=body,
                    content_clean=clean_text(body),
                    quality_score=min(1.0, score / 100),
                )
                posts_in += 1
            polite_sleep(2.5)
    return posts_in, comments_in


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-public", action="store_true", help="Ignora PRAW aunque haya creds.")
    args = parser.parse_args()

    settings = get_settings()
    if not args.force_public and settings.reddit_client_id and settings.reddit_client_secret:
        log("Modo: PRAW (con auth)")
        try:
            posts, comments = run_with_praw()
        except ImportError:
            log("praw no disponible, fallback a modo público", "warn")
            posts, comments = run_public()
    else:
        log("Modo: JSON público (sin auth)")
        posts, comments = run_public()

    log(f"posts: {posts} · comments: {comments}", "ok")


if __name__ == "__main__":
    main()
