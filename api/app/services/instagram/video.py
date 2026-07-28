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

SIN AUDIO, y es una DECISIÓN TOMADA, no una carencia pendiente de resolver
(jul-2026):

  - La música de Extremoduro tiene derechos e Instagram la detecta sola: no
    hace falta que nadie reclame, el sistema silencia o bloquea el reel. Y la
    biblioteca de audio licenciada de Instagram solo se puede elegir a mano
    desde la app, nunca por API — justo la vía por la que publicamos.
  - Poner música libre de derechos se descartó por criterio editorial: en un
    reel de un verso de Robe, un fondo genérico que no es de Extremoduro queda
    peor que el silencio.

Las guitarras de verdad entran por otra puerta: los CLIPS DE TERCEROS
(`video_clips.py`) conservan su audio original — un fan tocando, una entrevista,
un directo. Ahí el sonido es real y viene con el material.

Se incrusta una pista silenciosa porque algunos reproductores esperan un stream
de audio.
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
DUR_TOTAL = 7.0          # segundos
MIN_DUR = 3.0            # Instagram admite de 3 s; los cortos funcionan mejor

# CUÁNDO APARECE EL VERSO. La primera versión lo sacaba a los 2,2 s de 8 y el
# reel parecía otra cosa: medio vídeo pasaba sin que se leyera nada. Ahora entra
# casi de inmediato — en un feed, quien no lee algo en el primer segundo, sigue
# haciendo scroll.
ENTRADA_VERSO_S = 0.55
CORTE_S = 0.14           # transición seca, no un fundido largo

# RITMO. El motor tiene dos marchas y las gobierna el tono del post:
#   - "rock"   → cortes secos, zoom que late, flash y cierre en negro.
#   - "sobrio" → lo de antes: lento y sin sobresaltos. Para homenajes y
#     fallecimientos, donde el nervio visual desentona.
RITMO_ROCK = "rock"
RITMO_SOBRIO = "sobrio"


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


def _filtro_rock(frames_a: int, frames_b: int, duracion: float) -> str:
    """Secuencia con nervio: entrada seca, zoom que late, flash y cierre.

    Todo el movimiento lo hace ffmpeg sobre dos imágenes clave; no se generan
    fotogramas en Python. Las piezas:

      - la portada arranca ya con zoom rápido (`0.14*on`), no reposada;
      - el corte al verso es `fadeblack` de 0,14 s — un golpe, no un fundido;
      - sobre el verso, el zoom LATE (`sin`) en vez de subir liso: es lo que da
        sensación de pulso;
      - un flash blanco muy corto justo al entrar el texto;
      - cierre a negro al final.
    """
    ancho, alto = SIZE_REEL
    return (
        # Portada: zoom agresivo desde el primer fotograma.
        f"[0:v]zoompan=z='1+0.14*on/{frames_a}':d={frames_a}:"
        f"s={ancho}x{alto}:fps={FPS}[a];"
        # Verso: zoom base + latido. El seno hace que respire.
        f"[1:v]zoompan=z='1.06+0.035*sin(on/7)':d={frames_b}:"
        f"s={ancho}x{alto}:fps={FPS},"
        # Flash de entrada: blanco muy breve al aparecer el texto.
        f"fade=t=in:st=0:d=0.10:color=white,"
        # Cierre a negro.
        f"fade=t=out:st={max(duracion - ENTRADA_VERSO_S - 0.45, 0.1):.2f}:d=0.45[b];"
        f"[a][b]xfade=transition=fadeblack:duration={CORTE_S}:"
        f"offset={ENTRADA_VERSO_S:.2f}[v]"
    )


def _filtro_sobrio(frames_a: int, frames_b: int, duracion: float) -> str:
    """Sin nervio: para homenajes y temas delicados, donde el ritmo desentona."""
    ancho, alto = SIZE_REEL
    return (
        f"[0:v]zoompan=z='1+0.05*on/{frames_a}':d={frames_a}:"
        f"s={ancho}x{alto}:fps={FPS}[a];"
        f"[1:v]zoompan=z='1.05+0.04*on/{frames_b}':d={frames_b}:"
        f"s={ancho}x{alto}:fps={FPS},"
        f"fade=t=out:st={max(duracion - 1.6, 0.1):.2f}:d=0.8[b];"
        f"[a][b]xfade=transition=fade:duration=0.9:offset=1.1[v]"
    )


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

    # El ritmo lo decide el TONO del post, que ya calcula `tone.classify`: un
    # homenaje o un fallecimiento con cortes secos y flashes sería una falta de
    # tacto. Todo lo demás va con nervio.
    ritmo = RITMO_SOBRIO if topic.get("tone") == "sober" else RITMO_ROCK

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
        # `zoompan` trabaja fotograma a fotograma: 'on' es el índice actual.
        # El zoom se mantiene contenido (máx ~1.14): con el 1.18 del primer
        # intento, el recorte del encuadre se comía el final de los versos.
        filtro = (
            _filtro_sobrio(frames, frames, duracion)
            if ritmo == RITMO_SOBRIO
            else _filtro_rock(frames, frames, duracion)
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
