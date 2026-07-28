"""Vídeo propio: versos animados en formato reel (9:16).

Por qué existe: de las 387 publicaciones leídas del nicho, el **69% son vídeo**,
y el vídeo mediano rinde 4,06% de engagement frente al 1,97% de la imagen (n=266
vs 116). Cinco de las siete cuentas estudiadas publican >90% en vídeo. Nosotros
íbamos al 100% de foto estática.

Este módulo hace vídeo **enteramente nuestro**: el fondo sale del mismo motor de
`imaging` y el texto es un verso del corpus. Sin material de terceros y sin
riesgo de copyright — los clips ajenos son otra cosa y viven en `video_clips.py`.

CÓMO: en vez de generar cientos de fotogramas en Python, se componen DOS imágenes
clave (fondo limpio → fondo con el verso) y ffmpeg hace el trabajo: zoom lento
tipo Ken Burns sobre cada una y un fundido entre ambas. Sale barato y se ve como
un vídeo de verdad.

SIN AUDIO, y es una limitación consciente: la música de Extremoduro tiene
derechos y la biblioteca de audio de Instagram no se puede elegir por API. Un
reel mudo rinde menos que uno con música; ponerle música que no es nuestra no es
una opción. Se incrusta una pista silenciosa porque algunos reproductores
esperan un stream de audio.
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw

from app.services.instagram import config, imaging

logger = logging.getLogger(__name__)

# Formato vertical de reel.
SIZE_REEL = (1080, 1920)
FPS = 30
DUR_TOTAL = 8.0          # segundos
DUR_FUNDIDO = 1.2

# Instagram admite reels de 3 s a 15 min; los cortos funcionan mejor.
MIN_DUR = 3.0


def _fondo_limpio(topic: dict, seed: int) -> Image.Image:
    """Fondo cuadrado SIN texto, con la misma cascada que usa `imaging`.

    No se puede reutilizar `imaging.generate` aquí: esa función ya escribe el
    titular en la tarjeta, y el reel vuelve a escribir el verso encima — el
    primer intento salió con el verso duplicado y solapado consigo mismo.
    """
    pista = (topic.get("image_hint") or "").strip()
    thumb = (topic.get("image_hint_thumb") or "").strip()
    es_portada = topic.get("image_kind") == "cover"

    fondo, con_foto = None, False
    for url in (pista, thumb):
        if not url:
            continue
        try:
            fondo = imaging._fetch_image(url)
            con_foto = True
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("[IG] reel: no se pudo bajar %s (%s)", url[:60], exc)

    if fondo is None:
        categoria = topic.get("category", "Actualidad")
        motivo = imaging.MOODS.get(categoria, imaging.MOODS["Actualidad"])
        titulo = (topic.get("headline") or topic.get("title") or "").strip()
        try:
            fondo = imaging._ai_background(f"{titulo} — {motivo}", seed)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[IG] reel: arte IA falló (%s)", exc)
        if fondo is None:
            fondo = imaging._gradient_background(seed)

    return imaging._treat(fondo, has_photo=con_foto, is_cover=es_portada)


def _lienzo_vertical(cuadrada: Image.Image) -> Image.Image:
    """Encaja la tarjeta cuadrada en un lienzo 9:16 sin deformarla.

    La imagen se centra y las bandas de arriba y abajo se rellenan con una
    versión ampliada y desenfocada de ella misma, así el fondo no es un bloque
    plano y la pieza sigue leyéndose como una sola.
    """
    from PIL import ImageFilter

    ancho, alto = SIZE_REEL
    # Relleno: la propia imagen ampliada a pantalla completa y desenfocada.
    escala = alto / cuadrada.height
    relleno = cuadrada.resize(
        (int(cuadrada.width * escala), alto), Image.LANCZOS
    ).filter(ImageFilter.GaussianBlur(38))
    izq = (relleno.width - ancho) // 2
    lienzo = relleno.crop((izq, 0, izq + ancho, alto))
    lienzo = Image.blend(lienzo, Image.new("RGB", SIZE_REEL, imaging.COL_BG), 0.45)
    # La tarjeta, centrada.
    tarjeta = cuadrada.resize((ancho, ancho), Image.LANCZOS)
    lienzo.paste(tarjeta, (0, (alto - ancho) // 2))
    return lienzo


def _con_verso(base: Image.Image, verso: str, atribucion: str) -> Image.Image:
    """Segunda imagen clave: la misma, con el verso escrito encima."""
    img = base.copy()
    draw = ImageDraw.Draw(img)
    # Margen de SEGURIDAD, no estético: el zoom de ffmpeg amplía la imagen y se
    # come los bordes. Con zoom máximo 1.09 queda visible el 92% del ancho, así
    # que el texto tiene que caber muy dentro o se corta por la derecha (pasó).
    margen = 160
    ancho_texto = SIZE_REEL[0] - 2 * margen

    # Se limita a 5 líneas y se parte del cuerpo 76: en vertical, un verso a 96
    # ocupaba el ancho entero y se salía de caja por los lados.
    fuente, lineas, alto_linea = imaging._fit_text(
        draw, verso, ancho_texto, 700, 5, range(76, 39, -4)
    )
    total = len(lineas) * alto_linea
    y = (SIZE_REEL[1] - total) // 2

    # Velo oscuro tras el texto para que se lea sobre cualquier fondo.
    velo = Image.new("RGBA", SIZE_REEL, (0, 0, 0, 0))
    ImageDraw.Draw(velo).rectangle(
        [0, y - 70, SIZE_REEL[0], y + total + 110], fill=(13, 11, 10, 190)
    )
    img = Image.alpha_composite(img.convert("RGBA"), velo).convert("RGB")
    draw = ImageDraw.Draw(img)

    for ln in lineas:
        w = draw.textlength(ln, font=fuente)
        draw.text(((SIZE_REEL[0] - w) / 2, y), ln, font=fuente, fill=imaging.COL_PAPER)
        y += alto_linea

    if atribucion:
        f_attr = imaging._mono(20)
        w = imaging._tracked_width(draw, atribucion, f_attr, 3)
        imaging._draw_tracked(
            draw, ((SIZE_REEL[0] - w) / 2, y + 26), atribucion, f_attr,
            imaging.COL_MUTED, tracking=3,
        )

    # Marca al pie.
    # La marca va MUY dentro del alto por lo mismo que el texto: a 150 px del
    # borde el zoom la partía por la mitad.
    marca = "ENTRE INTERIORES"
    f_marca = imaging._mono(19)
    w = imaging._tracked_width(draw, marca, f_marca, 5)
    imaging._draw_tracked(
        draw, ((SIZE_REEL[0] - w) / 2, SIZE_REEL[1] - 280), marca, f_marca,
        imaging.COL_GRANATE, tracking=5,
    )
    return img


def _ffmpeg(args: list[str]) -> None:
    """Ejecuta ffmpeg y sube el error real si falla (no un exit code pelado)."""
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", *args],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {proc.stderr.strip()[:400]}")


def render_verse_reel(
    topic: dict, slot: int = 1, duracion: float = DUR_TOTAL
) -> str:
    """Genera el MP4 de un verso animado. Devuelve la ruta del fichero.

    El fondo lo resuelve el motor de imagen de siempre, así que un reel comparte
    identidad visual con las tarjetas: misma paleta, mismo tratamiento.
    """
    verso = (topic.get("headline") or topic.get("title") or "").strip()
    if not verso:
        raise ValueError("no hay verso que animar")
    corpus = topic.get("corpus") or {}
    atribucion = ""
    if corpus.get("song"):
        atribucion = f'«{corpus["song"]}»'
        if corpus.get("album"):
            atribucion += f' · {corpus["album"]}'

    duracion = max(duracion, MIN_DUR)
    seed = int(hashlib.md5(f"{verso}{slot}v".encode()).hexdigest(), 16) % 1_000_000
    os.makedirs(config.IMAGES_DIR, exist_ok=True)
    salida = os.path.join(config.IMAGES_DIR, f"reel_{seed}_{slot}.mp4")

    # 1) Fondo SIN texto → lienzo vertical → copia con el verso encima.
    limpia = _lienzo_vertical(_fondo_limpio(topic, seed))
    escrita = _con_verso(limpia, verso, atribucion)

    with tempfile.TemporaryDirectory() as tmp:
        f_limpia = os.path.join(tmp, "a.png")
        f_escrita = os.path.join(tmp, "b.png")
        limpia.save(f_limpia)
        escrita.save(f_escrita)

        frames = int(duracion * FPS)
        # Zoom lento sobre cada imagen clave (Ken Burns) y fundido entre ambas.
        # `zoompan` trabaja fotograma a fotograma: 'on' es el índice actual.
        # Zoom SUTIL (1.00→1.09 en total). Con el 1.18 del primer intento, el
        # recorte del encuadre se comía el final de los versos largos.
        filtro = (
            f"[0:v]zoompan=z='1+0.05*on/{frames}':d={frames}:"
            f"s={SIZE_REEL[0]}x{SIZE_REEL[1]}:fps={FPS}[a];"
            f"[1:v]zoompan=z='1.05+0.04*on/{frames}':d={frames}:"
            f"s={SIZE_REEL[0]}x{SIZE_REEL[1]}:fps={FPS}[b];"
            f"[a][b]xfade=transition=fade:duration={DUR_FUNDIDO}:"
            f"offset={max(duracion * 0.28, 1.0):.2f}[v]"
        )
        _ffmpeg([
            "-loop", "1", "-t", f"{duracion}", "-i", f_limpia,
            "-loop", "1", "-t", f"{duracion}", "-i", f_escrita,
            # Pista silenciosa: algunos reproductores esperan stream de audio.
            "-f", "lavfi", "-t", f"{duracion}", "-i", "anullsrc=r=44100:cl=stereo",
            "-filter_complex", filtro,
            "-map", "[v]", "-map", "2:a",
            "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-c:a", "aac", "-b:a", "64k",
            "-movflags", "+faststart", "-t", f"{duracion}",
            salida,
        ])

    tam = os.path.getsize(salida) / 1024 / 1024
    logger.info("[IG] reel generado: %s (%.1f MB, %.0fs)", salida, tam, duracion)
    return salida
