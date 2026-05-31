"""Generación de imágenes para Instagram — identidad «Entre Interiores».

Estética (alineada con la web, ver CLAUDE.md):
  - Paleta: granate #a83a3a sobre negro #0d0b0a, texto papel #ede4d3.
  - Tipografía: Cormorant Garamond (serif) para titulares y versos (itálica),
    JetBrains Mono para etiquetas/marca (uppercase, letterspacing).
  - Tono editorial nocturno, minimalista, "guiños sin copiar marcas".

Imagen de fondo, por orden de preferencia:
  1. Foto REAL con licencia libre (CC) del protagonista de la noticia,
     buscada por `photo_finder` (Wikimedia/Openverse). Se acredita al autor.
  2. Imagen destacada propia del artículo (posts del blog).
  3. Fondo artístico generado por IA, afín al tema (pollinations.ai, flux).
  4. Degradado granate propio (último recurso).

El texto se compone con Pillow sobre un tratamiento oscuro + degradado que
garantiza legibilidad. Resultado: contenido visual original de Entre Interiores
que respeta el copyright (solo fotos CC o arte propio).
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
MARGIN = 84

# --- Paleta «Entre Interiores» ---
COL_BG = (13, 11, 10)        # #0d0b0a negro profundo
COL_GRANATE = (168, 58, 58)  # #a83a3a granate
COL_PAPER = (237, 228, 211)  # #ede4d3 papel
COL_MUTED = (168, 159, 144)  # papel apagado (~62%)

# --- Fuentes reales de la identidad (empaquetadas en fonts/) ---
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_CG_ROMAN = os.path.join(_FONTS_DIR, "CormorantGaramond[wght].ttf")
_CG_ITALIC = os.path.join(_FONTS_DIR, "CormorantGaramond-Italic[wght].ttf")
_JB_BOLD = os.path.join(_FONTS_DIR, "JetBrainsMono-Bold.ttf")
_JB_REG = os.path.join(_FONTS_DIR, "JetBrainsMono-Regular.ttf")
# Fallback del sistema (presente en la imagen Docker vía fonts-dejavu-core).
_DEJAVU = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"

# Ambientes IA según categoría (abstracto, evocador, sin sujetos ni texto).
MOODS = {
    "Conciertos": "stage light beams, smoke and warm spotlights, concert energy",
    "Música": "vinyl record textures, sound waves, warm analog glow",
    "Colaboraciones": "two intertwining light trails, warm and cool tones meeting",
    "Grupos amigos": "campfire embers and guitar string light trails, brotherhood",
    "Cultura": "open book pages dissolving into light, poetic ink and paper",
    "Efemérides": "vintage calendar paper, sepia light, nostalgic dusty rays",
    "Curiosidades": "abstract curiosity spark, glowing ember of light, warm mystery",
    "Blog": "warm ink and paper texture, poetic literary atmosphere, soft light",
    "Actualidad": "dark crimson rock atmosphere, ember sparks rising, deep warm haze",
}


# --------------------------------------------------------------------------- #
# Fuentes
# --------------------------------------------------------------------------- #
def _cormorant(size: int, weight: int = 600, italic: bool = False) -> ImageFont.FreeTypeFont:
    """Cormorant Garamond variable, fijando el eje de peso (300-700)."""
    path = _CG_ITALIC if italic else _CG_ROMAN
    try:
        font = ImageFont.truetype(path, size)
        try:
            font.set_variation_by_axes([weight])
        except Exception:  # noqa: BLE001 — algunas builds no exponen el eje
            pass
        return font
    except Exception:  # noqa: BLE001
        try:
            return ImageFont.truetype(_DEJAVU, size)
        except Exception:  # noqa: BLE001
            return ImageFont.load_default(size)


def _mono(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    path = _JB_BOLD if bold else _JB_REG
    try:
        return ImageFont.truetype(path, size)
    except Exception:  # noqa: BLE001
        return ImageFont.load_default(size)


# --------------------------------------------------------------------------- #
# Helpers de texto
# --------------------------------------------------------------------------- #
def _tracked_width(draw, text, font, tracking) -> float:
    return sum(draw.textlength(c, font=font) + tracking for c in text) - tracking


def _draw_tracked(draw, xy, text, font, fill, tracking=6) -> float:
    """Dibuja texto con letterspacing (mono uppercase). Devuelve el ancho."""
    x, y = xy
    for c in text:
        draw.text((x, y), c, font=font, fill=fill)
        x += draw.textlength(c, font=font) + tracking
    return x - xy[0] - tracking


def _wrap(draw, text, font, max_width) -> list[str]:
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
    """Mayor tamaño de Cormorant SemiBold con el que el titular cabe en la caja."""
    for size in range(96, 47, -4):
        font = _cormorant(size, weight=600)
        lines = _wrap(draw, text, font, max_width)
        line_h = int(size * 1.06)
        if len(lines) <= max_lines and len(lines) * line_h <= max_height:
            return font, lines, line_h
    font = _cormorant(48, weight=600)
    lines = _wrap(draw, text, font, max_width)[:max_lines]
    return font, lines, 52


# --------------------------------------------------------------------------- #
# Fondos
# --------------------------------------------------------------------------- #
def _cover(img: Image.Image) -> Image.Image:
    """Recorta a cuadrado (cover) y escala a SIZE."""
    w, h = img.size
    s = min(w, h)
    left, top = (w - s) // 2, (h - s) // 2
    return img.crop((left, top, left + s, top + s)).resize(SIZE, Image.LANCZOS)


def _fetch_image(url: str, timeout: float = 60.0) -> Image.Image:
    headers = {
        "User-Agent": "EntreInteriores/1.0 (https://entreinteriores.com; "
        "difusion cultural Robe/Extremoduro)"
    }
    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
    return _cover(Image.open(io.BytesIO(resp.content)).convert("RGB"))


def _ai_background(mood: str, seed: int) -> Image.Image:
    prompt = (
        f"abstract artistic background, {mood}, deep dark crimson and charcoal "
        f"black tones, cinematic moody lighting, film grain texture, painterly "
        f"digital art, empty scene, no people no faces no text no words no logos"
    )
    url = (
        f"https://image.pollinations.ai/prompt/{quote(prompt)}"
        f"?width=1080&height=1080&seed={seed}&model=flux&nologo=true"
    )
    with httpx.Client(timeout=120.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
    return _cover(Image.open(io.BytesIO(resp.content)).convert("RGB"))


def _gradient_background(seed: int) -> Image.Image:
    """Degradado granate→negro propio (último recurso)."""
    img = Image.new("RGB", SIZE, COL_BG)
    draw = ImageDraw.Draw(img)
    for y in range(SIZE[1]):
        t = y / SIZE[1]
        r = int(COL_BG[0] + (COL_GRANATE[0] - COL_BG[0]) * (1 - t) * 0.30)
        g = int(COL_BG[1] + (COL_GRANATE[1] - COL_BG[1]) * (1 - t) * 0.12)
        b = int(COL_BG[2] + (COL_GRANATE[2] - COL_BG[2]) * (1 - t) * 0.12)
        draw.line([(0, y), (SIZE[0], y)], fill=(r, g, b))
    return img


def _treat(img: Image.Image, has_photo: bool, is_cover: bool = False) -> Image.Image:
    """Oscurece y aplica degradado inferior a negro para que el texto se lea.

    En portadas de disco el oscurecido es más suave (la portada es el sujeto,
    debe reconocerse), pero se mantiene el degradado inferior para el texto.
    """
    img = img.convert("RGB")
    if is_cover:
        img = ImageEnhance.Brightness(img).enhance(0.82)
    elif has_photo:
        img = ImageEnhance.Color(img).enhance(0.80)
        img = ImageEnhance.Brightness(img).enhance(0.60)
        img = ImageEnhance.Contrast(img).enhance(1.05)
    # Degradado vertical: limpio arriba, casi negro abajo (zona de texto).
    grad = Image.new("L", SIZE, 0)
    gd = ImageDraw.Draw(grad)
    for y in range(SIZE[1]):
        t = y / SIZE[1]
        v = 0.0 if t < 0.34 else ((t - 0.34) / 0.66)
        gd.line([(0, y), (SIZE[0], y)], fill=int(252 * (v ** 1.35)))
    img = Image.composite(Image.new("RGB", SIZE, COL_BG), img, grad)
    # Línea granate superior: firma de marca.
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, SIZE[0], 7], fill=COL_GRANATE)
    return img


# --------------------------------------------------------------------------- #
# Composición
# --------------------------------------------------------------------------- #
def generate(topic: dict, slot: int = 1) -> tuple[str, bool]:
    """Genera la imagen de un post. Devuelve (ruta_JPG, usó_foto_real)."""
    category = topic.get("category", "Actualidad")
    title = (topic.get("headline") or topic.get("title") or "Extremoduro").strip()
    image_hint = (topic.get("image_hint") or "").strip()
    credit = (topic.get("image_credit") or "").strip()
    image_kind = topic.get("image_kind", "photo")
    verse = topic.get("verse") or {}

    seed = int(hashlib.md5(f"{title}{slot}".encode()).hexdigest(), 16) % 1_000_000
    mood = MOODS.get(category, MOODS["Actualidad"])

    bg, used_photo = None, False
    if image_hint:
        try:
            bg = _fetch_image(image_hint)
            used_photo = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("[IMG] foto no usable (%s); voy a fondo IA", exc)
    if bg is None:
        try:
            bg = _ai_background(mood, seed)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[IMG] pollinations falló (%s); degradado propio", exc)
            bg = _gradient_background(seed)

    img = _treat(bg, used_photo, is_cover=(image_kind == "cover"))
    draw = ImageDraw.Draw(img)
    text_w = SIZE[0] - 2 * MARGIN

    # --- Kicker de categoría (arriba): mono uppercase con punto granate ---
    kicker_font = _mono(25, bold=True)
    ky = MARGIN
    draw.ellipse([MARGIN, ky + 6, MARGIN + 13, ky + 19], fill=COL_GRANATE)
    _draw_tracked(draw, (MARGIN + 26, ky), category.upper(), kicker_font,
                  COL_PAPER, tracking=5)

    # --- Anclado desde abajo: marca → crédito → verso → titular ---
    y = SIZE[1] - MARGIN

    # Marca (mono).
    brand_font = _mono(27, bold=True)
    sub_font = _mono(20, bold=False)
    y -= 30
    draw.text((MARGIN, y), "entreinteriores.com", font=sub_font, fill=COL_MUTED)
    y -= 36
    _draw_tracked(draw, (MARGIN, y), "ENTRE INTERIORES", brand_font, COL_PAPER, 3)
    # Divisor fino sobre la marca.
    y -= 22
    draw.line([(MARGIN, y), (SIZE[0] - MARGIN, y)], fill=(60, 52, 48), width=2)

    # Crédito de la foto (solo si es foto real con licencia).
    if used_photo and credit:
        cred_font = _mono(17, bold=False)
        y -= 30
        draw.text((MARGIN, y), f"Foto: {credit}", font=cred_font, fill=COL_MUTED)

    # Verso de Robe (Cormorant itálica) — ornamental, si cabe y existe.
    if verse.get("line"):
        v_font = _cormorant(40, weight=500, italic=True)
        v_lines = _wrap(draw, f"«{verse['line']}»", v_font, text_w)[:2]
        attribution = verse.get("artist", "")
        if verse.get("song"):
            attribution += f", «{verse['song']}»"
        if verse.get("year"):
            attribution += f" ({verse['year']})"
        attr_font = _mono(16, bold=False)
        y -= 30
        draw.text((MARGIN, y), attribution, font=attr_font, fill=COL_MUTED)
        for line in reversed(v_lines):
            y -= int(40 * 1.12)
            draw.text((MARGIN, y), line, font=v_font, fill=COL_PAPER)
        y -= 18

    # Titular (Cormorant SemiBold) con barra granate a la izquierda.
    headline_font, lines, line_h = _fit_headline(
        draw, title, text_w - 28, max_height=430, max_lines=5
    )
    block_h = len(lines) * line_h
    top = y - block_h
    draw.rectangle([MARGIN, top + 8, MARGIN + 6, top + block_h], fill=COL_GRANATE)
    ty = top
    for line in lines:
        draw.text((MARGIN + 28, ty), line, font=headline_font, fill=COL_PAPER)
        ty += line_h

    os.makedirs(config.IMAGES_DIR, exist_ok=True)
    path = os.path.join(config.IMAGES_DIR, f"post_{seed}_{slot}.jpg")
    img.convert("RGB").save(path, "JPEG", quality=92)
    logger.info("[IMG] Imagen generada: %s (foto_real=%s)", path, used_photo)
    return path, used_photo
