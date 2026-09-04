"""Renderiza carruseles de muestra a disco, sin BD de cola ni Graph API.

Hermano de `sample_cards.py`: sirve para revisar VISUALMENTE cómo queda la
secuencia de diapositivas antes de soltar un cambio de estilo. No publica nada
ni escribe en la cola.

Uso:
    python -m scripts.instagram.sample_carousel
    python -m scripts.instagram.sample_carousel --out /tmp/carruseles --quotes 3
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
from datetime import date

from app.db.models import InstagramQueueItem
from app.db.session import SessionLocal
from app.services.instagram import carousel, config, evergreen, publisher, tone

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="/tmp/carruseles")
    parser.add_argument("--quotes", type=int, default=2)
    parser.add_argument("--anecdotes", type=int, default=2)
    parser.add_argument("--ephemerides", type=int, default=1)
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    mix = {
        "quote": args.quotes,
        "anecdote": args.anecdotes,
        "ephemeris": args.ephemerides,
        "robe_quote": 0,
    }

    with SessionLocal() as db:
        for cand in evergreen.generate_batch(db, mix=mix):
            item = InstagramQueueItem(
                day=date.today(), slot=1, content_type=cand["content_type"],
                content_key=cand["content_key"], title=cand["title"][:300],
                category=cand.get("category"), summary=cand.get("summary"),
                status="proposed",
            )
            topic = publisher._topic_from_item(db, item)
            topic["content_type"] = item.content_type
            topic["corpus"] = publisher._corpus_context(db, item)
            topic["tone"] = tone.classify(topic["title"], topic["summary"])
            topic["verse"] = {}

            specs = carousel.plan(topic, item.content_type)
            if not specs:
                print(f"· [{item.content_type}] sin material para carrusel → foto única")
                continue

            rutas, _ = carousel.render(topic, specs, slot=1)
            destino = os.path.join(args.out, item.content_key.replace(":", "_"))
            os.makedirs(destino, exist_ok=True)
            for i, r in enumerate(rutas):
                shutil.copy(r, os.path.join(destino, f"{i:02d}_{specs[i]['layout']}.jpg"))
            print(f"✓ [{item.content_type}] {len(rutas)} diapositivas → {destino}")
            print(f"    {' → '.join(s['layout'] for s in specs)}")

    print(f"\nRevisa las imágenes en {args.out}")
    print(f"(config: carrusel {'ON' if config.CAROUSEL_ENABLED else 'OFF'})")


if __name__ == "__main__":
    main()
