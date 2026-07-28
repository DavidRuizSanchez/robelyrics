"""Imprime captions de muestra con candidatos REALES del corpus.

No toca la cola ni publica nada: genera candidatos evergreen como haría el cron,
construye el topic igual que `publisher.prepare` y saca el caption por pantalla.
Sirve para revisar el tono y la variedad antes de soltar un cambio de estilo.

Uso:
    python -m scripts.instagram.sample_captions
    python -m scripts.instagram.sample_captions --quotes 6 --anecdotes 2
    python -m scripts.instagram.sample_captions --solo-primera-linea
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

from app.db.models import InstagramQueueItem
from app.db.session import SessionLocal
from app.services.instagram import captions, evergreen, publisher, tone

logging.basicConfig(level=logging.WARNING)


def _item_de(cand: dict) -> InstagramQueueItem:
    """Item en memoria (NO se añade a la sesión: esto no escribe nada)."""
    return InstagramQueueItem(
        day=date.today(),
        content_type=cand["content_type"],
        content_key=cand["content_key"],
        title=cand["title"][:300],
        category=cand.get("category"),
        summary=cand.get("summary"),
        source_name=cand.get("source_name"),
        status="proposed",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quotes", type=int, default=4)
    parser.add_argument("--ephemerides", type=int, default=2)
    parser.add_argument("--anecdotes", type=int, default=2)
    parser.add_argument("--robe-quotes", type=int, default=2)
    parser.add_argument("--solo-primera-linea", action="store_true",
                        help="Solo la línea visible en el feed, para ver variedad.")
    args = parser.parse_args()

    mix = {
        "quote": args.quotes,
        "ephemeris": args.ephemerides,
        "anecdote": args.anecdotes,
        "robe_quote": args.robe_quotes,
    }

    with SessionLocal() as db:
        batch = evergreen.generate_batch(db, mix=mix)
        if not batch:
            raise SystemExit("Sin candidatos: ¿corpus vacío o todo deduplicado?")

        for cand in batch:
            item = _item_de(cand)
            topic = publisher._topic_from_item(db, item)
            topic["content_type"] = item.content_type
            topic["corpus"] = publisher._corpus_context(db, item)
            topic["tone"] = tone.classify(topic["title"], topic["summary"])
            topic["verse"] = {}          # el evergreen no lleva verso ornamental
            caption = captions.build(db, topic)

            if args.solo_primera_linea:
                print(f"[{item.content_type:11}] {caption.splitlines()[0]}")
            else:
                print("=" * 72)
                print(f"tipo: {item.content_type} · clave: {item.content_key}")
                print("-" * 72)
                print(caption)
                print()


if __name__ == "__main__":
    main()
