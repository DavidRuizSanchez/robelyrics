"""Genera reels de muestra a disco para revisarlos a ojo. No publica nada.

Hermano de `sample_cards.py` y `sample_carousel.py`. Extrae además unos
fotogramas, que es lo práctico para revisar sin abrir el vídeo.

Uso:
    python -m scripts.instagram.sample_reel
    python -m scripts.instagram.sample_reel --n 3 --out /tmp/reels
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
from datetime import date

from app.db.models import InstagramQueueItem
from app.db.session import SessionLocal
from app.services.instagram import evergreen, publisher, tone, video

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=2)
    parser.add_argument("--out", default="/tmp/reels")
    parser.add_argument("--duracion", type=float, default=video.DUR_TOTAL)
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    with SessionLocal() as db:
        candidatos = evergreen.generate_batch(
            db, mix={"quote": args.n, "ephemeris": 0, "anecdote": 0, "robe_quote": 0}
        )
        for cand in candidatos:
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

            ruta = video.render_verse_reel(topic, slot=1, duracion=args.duracion)
            destino = os.path.join(args.out, item.content_key.replace(":", "_"))
            os.makedirs(destino, exist_ok=True)
            shutil.copy(ruta, os.path.join(destino, "reel.mp4"))
            # Fotogramas de control: arranque, transición y final.
            for t in (0.5, args.duracion * 0.5, args.duracion - 0.5):
                subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t}",
                     "-i", ruta, "-frames:v", "1",
                     os.path.join(destino, f"frame_{t:.1f}s.png")],
                    check=False,
                )
            print(f"✓ {item.title[:52]}  →  {destino}")

    print(f"\nRevisa los vídeos y fotogramas en {args.out}")


if __name__ == "__main__":
    main()
