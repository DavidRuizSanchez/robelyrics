"""Detección de entradas que duplican un tema ya cubierto.

Vive aquí, y no dentro del script `scripts.blog.triage_pending`, porque el aviso
diario también lo necesita: decirle a alguien que tiene 13 entradas esperando no
le dice qué hacer con ellas, y «esta ya la publicaste» es el único veredicto que
no se deduce mirando el título en una lista. Es determinista y no gasta llamadas
al LLM, así que puede correr en cada envío del correo.

El resto del triage (citas en zona gris, contradicciones con el catálogo, gate de
rigor) sigue en el script: eso sí cuesta llamadas y latencia.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from app.db.models import Post

# Por encima de esto, dos títulos compiten por la misma búsqueda. MEDIDO contra
# la cola real del 07-09-2026, no elegido a ojo:
#   0.74  «La Evolución Musical de Extremoduro a Través de los Años»
#         vs «La Evolución Musical de Extremoduro: Un Viaje Transgresivo»
#   0.63  ídem vs «Extremoduro: La Evolución del Rock Transgresivo» (publicado)
#   0.64  «Robe: De Chapista a Ícono» vs «Robe: De Dosis Letal a la Leyenda»
#   0.53  «La Hoguera» vs «Pedrá en directo (1995)»  ← temas distintos
# Los tres primeros canibalizan; el cuarto no. El corte va entre 0.53 y 0.63.
# Se elige el lado generoso a propósito: esto SEÑALA para que mires, no borra.
UMBRAL_PARECIDO = 0.60

# Palabras que aparecen en casi todos los títulos del sitio y que, si cuentan,
# hacen que todo se parezca a todo.
VACIAS = {"de", "del", "la", "el", "los", "las", "un", "una", "y", "en", "a",
          "robe", "extremoduro", "su", "sus", "al", "por", "con"}


def normaliza(titulo: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", titulo.lower())
        if not unicodedata.combining(c)
    )
    palabras = [p for p in re.findall(r"[a-z0-9]+", sin_tildes) if p not in VACIAS]
    return " ".join(palabras)


def parecido(a: str, b: str) -> float:
    return SequenceMatcher(None, normaliza(a), normaliza(b)).ratio()


def duplicado_de(post: Post, otros: list[Post]) -> tuple[Post, float] | None:
    """El post publicado (o el pendiente más antiguo) que ya cubre este tema."""
    mejor: tuple[Post, float] | None = None
    for otro in otros:
        if otro.id == post.id:
            continue
        if (post.target_keyword_slug and
                post.target_keyword_slug == otro.target_keyword_slug):
            return otro, 1.0
        ratio = parecido(post.title, otro.title)
        if ratio >= UMBRAL_PARECIDO and (mejor is None or ratio > mejor[1]):
            mejor = (otro, ratio)
    return mejor
