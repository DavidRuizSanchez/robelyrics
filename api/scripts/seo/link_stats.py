"""Link juice interno: cuenta cuántos enlaces internos recibe cada entidad del
corpus desde el CONTENIDO (cuerpos de posts + seo_content) y escribe un snapshot
en `data/internal_link_stats.json` ({path: inbound_count}).

El autolinker usa este snapshot para POTENCIAR las páginas más débiles
(las que reciben menos enlaces) al elegir a quién enlazar, sin saltarse las
reglas de relevancia (solo reordena entre candidatos ya relevantes).

Pensado para correr recurrentemente (cron semanal), antes del rebalanceo
(`relink_existing`). NOTA: solo cuenta enlaces de CONTENIDO; los enlaces
estructurales (nav, footer, breadcrumbs) no se cuentan aquí.

Uso:
    python -m scripts.seo.link_stats            (escribe snapshot + reporta)
    python -m scripts.seo.link_stats --top 25   (cuántas débiles listar)
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from collections import Counter
from pathlib import Path

from app.db.models import Post, SeoContent
from app.db.session import SessionLocal
from app.services.entity_resolver import SITE_URL_DEFAULT, build_corpus_index

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# `data/` es read-only en prod; escribe a /tmp y se copia a data/.
OUT_PATH = Path("/tmp/internal_link_stats.json")
_HREF = re.compile(r"\]\((https?://[^)\s]+|/[^)\s]+)\)")


def _to_path(url: str, base: str) -> str:
    if url.startswith(base):
        url = url[len(base):]
    return "/" + url.strip("/")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    base = SITE_URL_DEFAULT.rstrip("/")
    with SessionLocal() as db:
        index = build_corpus_index(db)
        # Inicializa a 0 todas las entidades (las huérfanas también cuentan).
        counts: Counter[str] = Counter()
        url_by_path = {}
        for e in index:
            p = _to_path(e["url"], base)
            counts[p] = 0
            url_by_path[p] = e

        bodies = [b for (b,) in db.query(Post.body_md).all() if b]
        bodies += [b for (b,) in db.query(SeoContent.body_md).all() if b]
        for body in bodies:
            for m in _HREF.finditer(body):
                p = _to_path(m.group(1), base)
                if p in counts:
                    counts[p] += 1

    OUT_PATH.write_text(json.dumps(dict(counts), ensure_ascii=False, indent=2))
    total_links = sum(counts.values())
    orphans = [p for p, c in counts.items() if c == 0]
    logger.info(
        "Snapshot escrito %s · %d entidades · %d enlaces de contenido · %d huérfanas",
        OUT_PATH, len(counts), total_links, len(orphans),
    )
    logger.info("Páginas MÁS DÉBILES (menos enlaces entrantes):")
    for p, c in sorted(counts.items(), key=lambda kv: (kv[1], kv[0]))[:args.top]:
        tipo = url_by_path.get(p, {}).get("type", "?")
        logger.info("  %2d  [%-7s] %s", c, tipo, p)


if __name__ == "__main__":
    main()
