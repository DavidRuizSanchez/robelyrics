"""Agregador unificado de noticias del universo Robe / Extremoduro.

Descarga las fuentes de `data/news_sources.yaml` a la tabla `news_items`. Es
el almacén ÚNICO del que beben los dos consumidores:

  - blog       (`scripts.blog.scrape_news`): filtra `policy` con 'blog',
                reescribe con voz editorial y crea propuestas.
  - instagram  (`scripts.instagram.*`): selecciona temas del día y publica
                enlazando y atribuyendo al medio original.

Respeto de derechos de autor: solo se guarda titular + enlace + extracto
breve + atribución de fuente, igual que un agregador tipo Google News. Nunca
se reproduce el cuerpo del artículo.

Workflow:
    cron diario 08:00 → fetch de cada fuente → filtro relevancia + antigüedad
    → dedup por URL → upsert en news_items → purga de noticias > 7 días.

Uso:
    python -m scripts.news.aggregate
    python -m scripts.news.aggregate --dry-run
    python -m scripts.news.aggregate --source gn_robe
"""
from __future__ import annotations

import argparse
import html
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import feedparser
import httpx
import yaml
from sqlalchemy import delete, func, select

from app.db.models import NewsItem, NewsSourceRun
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SOURCES_PATH = Path("/app/data/news_sources.yaml")
HTTP_TIMEOUT = 30.0
MAX_NEWS_AGE_DAYS = 7
MAX_ENTRIES_PER_SOURCE = 30

# Google News y Reddit rechazan el User-Agent por defecto: usamos uno de
# navegador y descargamos con httpx; feedparser solo parsea el contenido.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def load_config() -> dict:
    with SOURCES_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def gnews_url(query: str) -> str:
    """Construye la URL del feed RSS de búsqueda de Google News."""
    return (
        f"https://news.google.com/rss/search?q={quote(query)}"
        "&hl=es&gl=ES&ceid=ES:es"
    )


# --------------------------------------------------------------------------- #
# Limpieza y clasificación
# --------------------------------------------------------------------------- #
def _clean(text: str, limit: int = 280) -> str:
    """Quita HTML y recorta a un extracto breve (uso legítimo / fair use)."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def _clean_title(title: str) -> str:
    """Quita el sufijo ' - Publicación' que añade Google News al titular."""
    return re.sub(r"\s+[-–|]\s+[^-–|]{2,45}$", "", title).strip() or title


def _score(title: str, summary: str, weight: float, keywords: dict) -> float:
    """Puntúa la relevancia temática por keywords presentes."""
    blob = f"{title} {summary}".lower()
    score = 0.0
    for kw, pts in keywords.items():
        if kw in blob:
            score += pts
    return round(score * weight, 2)


def _categorize(title: str, summary: str, friend_bands: list[str]) -> str:
    """Clasifica la noticia en una categoría temática."""
    blob = f"{title} {summary}".lower()
    if any(g in blob for g in friend_bands):
        return "Grupos amigos"
    if any(w in blob for w in ("colaboración", "versión", "tributo", "feat", "dueto")):
        return "Colaboraciones"
    if any(w in blob for w in ("concierto", "gira", "festival", "directo", "entradas")):
        return "Conciertos"
    if any(w in blob for w in ("disco", "álbum", "single", "canción", "tema nuevo")):
        return "Música"
    if any(w in blob for w in ("entrevista", "libro", "documental", "poesía", "poema")):
        return "Cultura"
    if any(w in blob for w in ("aniversario", "efeméride", "hace", "años")):
        return "Efemérides"
    return "Actualidad"


def _is_relevant(title: str, summary: str, must_mention: list[str]) -> bool:
    """Filtro mínimo: la noticia debe mencionar el universo Robe / Extremoduro."""
    blob = f"{title} {summary}".lower()
    return any(k in blob for k in must_mention)


def _parse_published(entry) -> datetime | None:
    """Devuelve la fecha de publicación (UTC) si el feed la trae."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------- #
# Fetch
# --------------------------------------------------------------------------- #
def _download(url: str, verify: bool):
    """Descarga y parsea un feed. `verify` controla la verificación TLS."""
    with httpx.Client(
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        verify=verify,
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return feedparser.parse(resp.content)


def fetch_source(src: dict, relevance: dict) -> list[dict]:
    """Descarga y parsea una fuente. Devuelve los items relevantes y recientes."""
    kind = src.get("kind", "rss")
    if kind == "gnews":
        url = gnews_url(src["query"])
    elif kind == "rss":
        url = src["url"]
    else:
        logger.warning("Fuente %s: kind '%s' no soportado", src["key"], kind)
        return []

    try:
        feed = _download(url, verify=True)
    except httpx.ConnectError as exc:
        # Algunas webs tienen el certificado mal configurado; reintento sin
        # verificar TLS (solo leemos titulares públicos, sin enviar datos).
        if "CERTIFICATE" in str(exc).upper() or "SSL" in str(exc).upper():
            logger.warning("  · %s: TLS inválido, reintento sin verificar", src["name"])
            feed = _download(url, verify=False)
        else:
            raise RuntimeError(f"fetch falló: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"fetch falló: {exc}") from exc

    must_mention = relevance.get("must_mention", [])
    keywords = relevance.get("keywords", {})
    friend_bands = relevance.get("friend_bands", [])
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_NEWS_AGE_DAYS)

    items: list[dict] = []
    for entry in feed.entries[:MAX_ENTRIES_PER_SOURCE]:
        title = _clean_title(_clean(entry.get("title", ""), 200))
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue

        summary = _clean(entry.get("summary", entry.get("description", "")))
        # Google News repite el titular como summary: si coincide, lo vaciamos.
        if summary and title[:60].lower() in summary.lower():
            summary = ""

        if not _is_relevant(title, summary, must_mention):
            continue

        published = _parse_published(entry)
        if published and published < cutoff:
            continue  # noticia demasiado vieja

        # Medio real: los feeds de Google News traen el editor original en
        # <source> (EL PAÍS, Cadena SER…). Si no, queda el nombre del feed.
        medium = None
        src_el = entry.get("source")
        if isinstance(src_el, dict):
            medium = (src_el.get("title") or "").strip() or None

        items.append({
            "title": title[:300],
            "url": link[:700],
            "source_key": src["key"],
            "source_name": src["name"],
            "source_medium": medium[:200] if medium else None,
            "summary": summary,
            "category": _categorize(title, summary, friend_bands),
            "policy": src["policy"],
            "relevance_score": _score(
                title, summary, float(src.get("weight", 1.0)), keywords
            ),
            "published_at": published,
        })
    return items


# --------------------------------------------------------------------------- #
# Persistencia
# --------------------------------------------------------------------------- #
def purge_old(db) -> int:
    """Borra noticias con más de MAX_NEWS_AGE_DAYS días. Devuelve cuántas.

    La fecha efectiva es la de publicación; si el feed no la trae, la de
    descarga. El FK de instagram_queue es ON DELETE SET NULL, así que la cola
    conserva su snapshot del tema aunque se purgue la noticia original.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_NEWS_AGE_DAYS)
    result = db.execute(
        delete(NewsItem).where(
            func.coalesce(NewsItem.published_at, NewsItem.fetched_at) < cutoff
        )
    )
    db.commit()
    return result.rowcount or 0


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe en la BD; solo informa.")
    parser.add_argument("--source", help="Limita a una fuente por su `key`.")
    args = parser.parse_args()

    if not SOURCES_PATH.exists():
        logger.error("No se encuentra %s", SOURCES_PATH)
        return

    cfg = load_config()
    relevance = cfg.get("relevance", {})
    sources = [s for s in cfg.get("sources", []) if s.get("enabled", True)]
    if args.source:
        sources = [s for s in sources if s.get("key") == args.source]
    if not sources:
        logger.error("No hay fuentes que procesar")
        return

    logger.info("Agregando noticias de %d fuentes…", len(sources))
    total_new = 0
    total_relevant = 0
    errors = 0

    with SessionLocal() as db:
        for src in sources:
            run = NewsSourceRun(source_name=src["name"])
            db.add(run)
            db.commit()
            db.refresh(run)

            try:
                items = fetch_source(src, relevance)
            except Exception as exc:  # noqa: BLE001
                logger.error("  · %-40s ERROR %s", src["name"], exc)
                run.error = str(exc)[:1000]
                run.finished_at = datetime.now(timezone.utc)
                db.commit()
                errors += 1
                continue

            run.items_found = len(items)
            new_here = 0
            for item in items:
                total_relevant += 1
                if args.dry_run:
                    continue
                exists = db.execute(
                    select(NewsItem.id).where(NewsItem.url == item["url"])
                ).scalar_one_or_none()
                if exists is not None:
                    continue
                db.add(NewsItem(**item))
                db.commit()
                new_here += 1

            run.items_inserted = new_here
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            total_new += new_here
            logger.info(
                "  · %-40s %3d nuevas / %3d relevantes",
                src["name"], new_here, len(items),
            )

        purged = 0
        if not args.dry_run:
            purged = purge_old(db)

    logger.info(
        "Run terminado: %d nuevas · %d relevantes · %d purgadas · %d errores",
        total_new, total_relevant, purged, errors,
    )


if __name__ == "__main__":
    main()
