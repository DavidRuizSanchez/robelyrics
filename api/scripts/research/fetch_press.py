"""Descarga URLs de prensa, blogs y papers desde data/press_urls.yaml.

Estructura del YAML:
  press_seo_only: [{url, title, author, kind}, ...]   # for_seo_only=True
  press:          [{url, title, author, kind}, ...]   # for_seo_only=False

Cada URL se descarga, se extrae texto con BeautifulSoup (reusa
extract_article_text de fetch_blogs.py), se filtra por relevancia y se
upserts como InterpretationSource. Sleep 2s entre dominios consecutivos
del mismo host para no abusar.

Para PDFs (papers académicos) usamos pypdf si está disponible; si no,
intentamos un get HTTP y tratamos la respuesta como texto plano si el
content-type lo indica, o saltamos con warning.

Ejecución:
  docker compose exec api python -m scripts.research.fetch_press
"""
from __future__ import annotations

import argparse
import io
import time
from typing import Any

import httpx
import yaml

from scripts.research.common import (
    DATA_DIR,
    clean_text,
    get_session,
    log,
    upsert_source,
)
from scripts.research.fetch_blogs import (
    HEADERS,
    extract_article_text,
    is_relevant,
)

PRESS_YAML = DATA_DIR / "press_urls.yaml"
MIN_CONTENT_CHARS = 400
SLEEP_SAME_HOST = 2.0


def load_press_yaml() -> dict[str, list[dict[str, Any]]]:
    if not PRESS_YAML.exists():
        log(f"no existe {PRESS_YAML}", "err")
        return {}
    with PRESS_YAML.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def fetch_url(client: httpx.Client, url: str) -> tuple[str | None, str | None]:
    """Devuelve (text, content_type). text=None si fallo."""
    try:
        r = client.get(url, headers=HEADERS, follow_redirects=True)
    except httpx.HTTPError as e:
        log(f"  http error {url}: {e}", "warn")
        return None, None
    if r.status_code != 200:
        log(f"  {r.status_code} {url}", "warn")
        return None, None
    ctype = r.headers.get("content-type", "").lower()
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        # Devolvemos los bytes en .text como base64 NO; los procesamos aparte.
        # Para mantener tipos consistentes devolvemos None aquí y el caller
        # se encarga de PDFs vía r.content (re-fetch).
        return None, "pdf"
    return r.text, ctype


def extract_pdf_text(client: httpx.Client, url: str) -> str | None:
    """Intenta extraer texto de un PDF con pypdf si está instalado."""
    try:
        from pypdf import PdfReader
    except ImportError:
        log(f"  pypdf no instalado, saltando PDF {url}", "warn")
        return None
    try:
        r = client.get(url, headers=HEADERS, follow_redirects=True, timeout=30)
        if r.status_code != 200:
            log(f"  pdf {r.status_code} {url}", "warn")
            return None
        reader = PdfReader(io.BytesIO(r.content))
        chunks: list[str] = []
        for page in reader.pages:
            try:
                chunks.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001
                continue
        text = "\n".join(chunks)
        return text or None
    except Exception as e:  # noqa: BLE001
        log(f"  pdf parse error {url}: {e}", "warn")
        return None


def process_entry(
    client: httpx.Client,
    db,
    entry: dict[str, Any],
    *,
    for_seo_only: bool,
    last_host: dict[str, float],
) -> bool:
    url = entry.get("url")
    if not url:
        return False

    # Pequeño rate-limit por host
    from urllib.parse import urlparse
    host = urlparse(url).netloc
    elapsed = time.monotonic() - last_host.get(host, 0.0)
    if elapsed < SLEEP_SAME_HOST:
        time.sleep(SLEEP_SAME_HOST - elapsed)
    last_host[host] = time.monotonic()

    text_html, ctype = fetch_url(client, url)
    raw: str | None = None
    cleaned: str | None = None

    if ctype == "pdf" or url.lower().endswith(".pdf"):
        raw = extract_pdf_text(client, url)
        if raw is None:
            return False
        cleaned = clean_text(raw)
    elif text_html is not None:
        article = extract_article_text(text_html)
        if not article:
            log(f"  sin texto extraíble en {url}", "warn")
            return False
        if len(article) < MIN_CONTENT_CHARS:
            log(f"  contenido demasiado corto ({len(article)} chars) {url}", "warn")
            return False
        if not is_relevant(article):
            log(f"  no relevante (sin términos Robe/Extremoduro/Iniesta) {url}", "warn")
            return False
        raw = text_html
        cleaned = clean_text(article)
    else:
        return False

    upsert_source(
        db,
        kind=entry.get("kind", "press"),
        url=url,
        title=entry.get("title"),
        author=entry.get("author"),
        content_raw=raw,
        content_clean=cleaned,
        quality_score=0.7 if for_seo_only else 0.6,
        for_seo_only=for_seo_only,
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--section",
        choices=["both", "seo_only", "press"],
        default="both",
        help="qué sección del YAML procesar",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="solo procesar las primeras N URLs (debug)",
    )
    args = parser.parse_args()

    data = load_press_yaml()
    if not data:
        return

    sections = []
    if args.section in ("both", "seo_only"):
        sections.append(("press_seo_only", True, data.get("press_seo_only", []) or []))
    if args.section in ("both", "press"):
        sections.append(("press", False, data.get("press", []) or []))

    total_ok = 0
    total_fail = 0

    last_host: dict[str, float] = {}
    with httpx.Client(timeout=20) as client, get_session() as db:
        for section_name, for_seo_only, entries in sections:
            log(f"=== sección {section_name} · {len(entries)} URLs · for_seo_only={for_seo_only} ===")
            count = 0
            for entry in entries:
                if args.limit and count >= args.limit:
                    break
                count += 1
                ok = process_entry(
                    client, db, entry,
                    for_seo_only=for_seo_only,
                    last_host=last_host,
                )
                if ok:
                    total_ok += 1
                    log(f"  ✓ {entry['title'][:80]}", "ok")
                else:
                    total_fail += 1

    log(f"upserts ok: {total_ok} · fallos: {total_fail}", "ok")


if __name__ == "__main__":
    main()
