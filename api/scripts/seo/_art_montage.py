"""Mosaico de QA: descarga el arte IA de temas/conceptos (image_url) y compone
una rejilla etiquetada en /tmp/art_montage.jpg para revisarlas de un vistazo.

Uso:  python -m scripts.seo._art_montage
"""
from __future__ import annotations

import io

import httpx
from PIL import Image, ImageDraw, ImageFont

from app.db.models import Concept, Theme
from app.db.session import SessionLocal

CELL_W, CELL_H, LABEL_H, COLS = 460, 345, 38, 3
_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def main() -> None:
    items: list[tuple[str, str]] = []
    with SessionLocal() as db:
        for model, tag in ((Theme, "theme"), (Concept, "concept")):
            for e in db.query(model).order_by(model.slug).all():
                if e.image_url:
                    items.append((f"{tag}/{e.slug}", e.image_url))

    rows = (len(items) + COLS - 1) // COLS
    sheet = Image.new("RGB", (CELL_W * COLS, (CELL_H + LABEL_H) * rows), (20, 16, 16))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(_FONT, 14)
    except Exception:  # noqa: BLE001
        font = ImageFont.load_default()

    with httpx.Client(timeout=40, follow_redirects=True) as c:
        for i, (label, url) in enumerate(items):
            x = (i % COLS) * CELL_W
            y = (i // COLS) * (CELL_H + LABEL_H)
            try:
                r = c.get(url)
                img = Image.open(io.BytesIO(r.content)).convert("RGB")
                img = img.resize((CELL_W, CELL_H))
                sheet.paste(img, (x, y))
            except Exception:  # noqa: BLE001
                draw.rectangle([x, y, x + CELL_W, y + CELL_H], fill=(60, 20, 20))
            draw.text((x + 6, y + CELL_H + 5), label, font=font, fill=(237, 228, 211))

    sheet.save("/tmp/art_montage.jpg", "JPEG", quality=88)
    print(f"montaje: {len(items)} imágenes ({COLS} cols) -> /tmp/art_montage.jpg")
    for i, (label, _) in enumerate(items):
        print(f"  [{i // COLS},{i % COLS}] #{i} {label}")


if __name__ == "__main__":
    main()
