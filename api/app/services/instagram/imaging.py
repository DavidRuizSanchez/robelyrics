"""Generación de imágenes para Instagram — 100% originales, sin copyright.

Estrategia legal:
  - El fondo es arte abstracto generado por IA (pollinations.ai, modelo flux,
    gratuito). Se piden escenas SIN personas, SIN texto, SIN logos → no se
    reproduce ninguna obra protegida ni la imagen de nadie.
  - Alternativa para posts del blog: la imagen destacada propia del artículo.
  - El texto se compone con Pillow sobre el fondo (tarjeta de diseño propio).
  - Resultado: contenido visual 100% original de Entre Interiores.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
from urllib.parse import quote

import httpx
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from app.services.instagram import config

logger = logging.getLogger(__name__)

SIZE = config.IMG_SIZE  # (1080, 1080)

# Paleta Entre Interiores (rock, tierra, brasa).
COL_BG = (14, 12, 16)
COL_ACCENT = (214, 92, 42)      # naranja brasa
COL_TEXT = (245, 242, 238)
COL_MUTED = (170, 165, 160)

# Fuentes DejaVu (instaladas en la imagen Docker vía fonts-dejavu-core).
_FONT_SERIF_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
_FONT_SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONT_SANS_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Ambientes IA según categoría (abstracto, evocador, sin sujetos).
MOODS = {
    "Conciertos": "stage light beams, smoke and warm spotlights, concert energy",
    "Música": "vinyl record textures, sound waves, warm analog glow",
    "Colaboraciones": "two intertwining light trails, warm and cool tones meeting",
    "Grupos amigos": "campfire embers and guitar string light trails, brotherhood warmth",
    "Cultura": "open book pages dissolving into light, poetic ink and paper texture",
    "Efemérides": "vintage calendar paper, sepia light, nostalgic dusty rays",
    "Curiosidades": "abstract curiosity spark, glowing question of light, warm mystery",
    "Blog": "warm ink and paper texture, poetic literary atmosphere, soft light",
    "Actualidad": "dramatic rock atmosphere, ember sparks rising, dark warm haze",
}


def _font(size: int, *, serif: bool = False, bold: bool = True) -> ImageFont.FreeTypeFont:
    """Carga una fuente DejaVu con fallback al default de Pillow."""
    if serif:
        path = _FONT_SERIF_BOLD
    else:
        path = _FONT_SANS_BOLD if bold else _FONT_SANS
    try:
        return ImageFont.truetype(path, size)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default()


def _ai_background(mood: str, seed: int) -> Image.Image:
    """Descarga un fondo abstracto de pollinations.ai (flux, gratuito)."""
    prompt = (
        f"abstract artistic background, {mood}, deep dark warm tones, "
        f"ember orange and charcoal black, cinematic moody lighting, "
        f"grain texture, painterly digital art, empty scene, "
        f"no people no faces no text no words no letters no logos"
    )
    url = (
        f"https://image.pollinations.ai/prompt/{quote(prompt)}"
        f"?width=1080&height=1080&seed={seed}&model=flux&nologo=true"
    )
    with httpx.Client(timeout=120.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    return img.resize(SIZE)


def _gradient_background(seed: int) -> Image.Image:
    """Fondo de degradado propio (fallback si la IA no responde)."""
    img = Image.new("RGB", SIZE, COL_BG)
    draw = ImageDraw.Draw(img)
    for y in range(SIZE[1]):
        t = y / SIZE[1]
        r = int(COL_BG[0] + (COL_ACCENT[0] - COL_BG[0]) * t * 0.35)
        g = int(COL_BG[1] + (COL_ACCENT[1] - COL_BG[1]) * t * 0.20)
        b = int(COL_BG[2] + (COL_ACCENT[2] - COL_BG[2]) * t * 0.15)
        draw.line([(0, y), (SIZE[0], y)], fill=(r, g, b))
    return img


def _hero_background(url: str) -> Image.Image:
    """Descarga la imagen destacada de un artículo del blog, recortada a cuadrado."""
    # User-Agent solo-ASCII: las cabeceras HTTP no admiten caracteres no-latin1.
    headers = {
        "User-Agent": "EntreInteriores/1.0 (https://entreinteriores.com; "
        "difusion cultural Robe/Extremoduro)"
    }
    with httpx.Client(timeout=60.0, headers=headers, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    w, h = img.size
    s = min(w, h)
    left, top = (w - s) // 2, (h - s) // 2
    return img.crop((left, top, left + s, top + s)).resize(SIZE)


def _darken(img: Image.Image, light: bool = False) -> Image.Image:
    """Oscurece el fondo y añade viñeta para que el texto sea legible."""
    img = ImageEnhance.Brightness(img).enhance(0.72 if light else 0.55)
    img = ImageEnhance.Contrast(img).enhance(1.0 if light else 1.05)
    overlay = Image.new("L", SIZE, 0)
    od = ImageDraw.Draw(overlay)
    for y in range(SIZE[1]):
        t = y / SIZE[1]
        od.line([(0, y), (SIZE[0], y)], fill=int(200 * (t ** 1.4)))
    black = Image.new("RGB", SIZE, (0, 0, 0))
    return Image.composite(black, img, overlay)


def _wrap(draw, text, font, max_width) -> list[str]:
    """Parte el texto en líneas que caben en max_width (medición real)."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= max_width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit_headline(draw, text, max_width, max_height, max_lines):
    """Elige el mayor tamaño de fuente con el que el titular cabe en la caja."""
    for size in range(70, 33, -4):
        font = _font(size, serif=True)
        lines = _wrap(draw, text, font, max_width)
        line_h = size + 14
        if len(lines) <= max_lines and len(lines) * line_h <= max_height:
            return font, lines, line_h
    font = _font(34, serif=True)
    lines = _wrap(draw, text, font, max_width)[:max_lines]
    return font, lines, 48


def generate(topic: dict, slot: int = 1) -> tuple[str, bool]:
    """Genera la imagen de un post.

    Devuelve (ruta_del_JPG, usó_foto_real). El segundo valor permite al
    llamante saber si la imagen es una foto con licencia (y por tanto si
    procede acreditar al autor en el caption) o un fondo IA abstracto.
    """
    category = topic.get("category", "Actualidad")
    title = (topic.get("headline") or topic.get("title") or "Extremoduro").strip()
    summary = topic.get("summary", "")
    image_hint = (topic.get("image_hint") or "").strip()

    seed = int(hashlib.md5(f"{title}{slot}".encode()).hexdigest(), 16) % 1_000_000
    mood = MOODS.get(category, MOODS["Actualidad"])

    # Posts del blog: imagen destacada real. Resto: fondo IA abstracto.
    bg, es_hero = None, False
    if image_hint:
        try:
            bg = _hero_background(image_hint)
            es_hero = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("[IMG] imagen del blog no usable (%s); uso fondo IA", exc)
    if bg is None:
        try:
            bg = _ai_background(mood, seed)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[IMG] pollinations falló (%s); uso degradado propio", exc)
            bg = _gradient_background(seed)

    img = _darken(bg, light=es_hero)
    draw = ImageDraw.Draw(img)
    margin = 80
    text_w = SIZE[0] - 2 * margin

    # --- Chip de categoría (arriba) ---
    chip_font = _font(30, bold=True)
    chip_text = category.upper()
    cw = draw.textlength(chip_text, font=chip_font)
    draw.rounded_rectangle(
        [margin, margin, margin + cw + 50, margin + 56],
        radius=28, fill=COL_ACCENT,
    )
    draw.text((margin + 25, margin + 11), chip_text, font=chip_font, fill=(20, 14, 10))

    # --- Footer de marca (anclado abajo) ---
    foot_y = SIZE[1] - 116
    draw.text((margin, foot_y), "ENTRE INTERIORES",
              font=_font(34, bold=True), fill=COL_TEXT)
    draw.text((margin, foot_y + 46),
              "entreinteriores.com · Robe & Extremoduro",
              font=_font(26, bold=False), fill=COL_MUTED)

    # --- Extracto breve (encima del footer) ---
    sub_bottom = foot_y - 34
    if summary:
        sub_font = _font(30, bold=False)
        short = (
            summary if len(summary) <= 160
            else summary[:160].rsplit(" ", 1)[0] + "…"
        )
        sub_lines = _wrap(draw, short, sub_font, text_w)[:3]
        sy = sub_bottom - len(sub_lines) * 40
        headline_bottom = sy - 28
        for line in sub_lines:
            draw.text((margin, sy), line, font=sub_font, fill=COL_MUTED)
            sy += 40
    else:
        headline_bottom = sub_bottom

    # --- Titular: auto-ajuste y anclado por su parte inferior ---
    headline_font, lines, line_h = _fit_headline(
        draw, title, text_w, max_height=440, max_lines=6
    )
    hy = headline_bottom - len(lines) * line_h
    draw.rectangle([margin, hy - 34, margin + 120, hy - 26], fill=COL_ACCENT)
    for line in lines:
        draw.text((margin, hy), line, font=headline_font, fill=COL_TEXT)
        hy += line_h

    # --- Guardar ---
    os.makedirs(config.IMAGES_DIR, exist_ok=True)
    path = os.path.join(config.IMAGES_DIR, f"post_{seed}_{slot}.jpg")
    img.convert("RGB").save(path, "JPEG", quality=92)
    logger.info("[IMG] Imagen generada: %s", path)
    return path, es_hero
