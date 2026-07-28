"""Motor de comunidad: arrancar la conversación en cada post.

Sale directamente del benchmark. Las tres cuentas del nicho con mejor
engagement relativo —@robe_dice_ (4,6-7,6%), @robeenelalma (1,5-7,2%) y
@entrerobeyextremo (18-203%)— hacen todas lo mismo: **se comentan a sí mismas**
nada más publicar, con la pregunta del caption o una frase que la amplía. Un
hilo que empieza vacío se queda vacío; uno que ya tiene un comentario invita.

Lo que NO se hace aquí, y es deliberado: nada de likes ni follows automáticos.
No existe endpoint oficial en la Graph API y hacerlo por vía no oficial pondría
en riesgo la única cuenta del proyecto. Además, los datos del propio benchmark
dicen que la palanca está en co-publicar, no en repartir likes: los posts
colaborativos de @donrobertoiniesta hacían 623-7.273 me gusta frente a los
100-200 de su contenido propio.
"""
from __future__ import annotations

import logging
import re

from app.services.instagram import graph_api

logger = logging.getLogger(__name__)

# La pregunta del caption, que es lo que mejor funciona como primer comentario:
# repetirla arriba del hilo deja claro que se espera respuesta.
_PREGUNTA = re.compile(r"^¿[^\n]{8,180}\?$", re.MULTILINE)

# Si el post no llevaba pregunta (tono sobrio, por ejemplo), se usa una frase
# que amplía sin exigir nada. Nunca se inventa contenido: son fórmulas de
# conversación, no datos.
CIERRES = (
    "Se admiten discrepancias por aquí abajo. 👇",
    "Contad, que esto se lee.",
    "¿Lo veis igual?",
)


def primer_comentario(caption: str) -> str | None:
    """Texto con el que arrancar el hilo, o None si no procede.

    Prioridad: la pregunta que ya lleva el caption. Es lo que hace el nicho y
    evita meter un texto nuevo que no case con la pieza.
    """
    texto = (caption or "").strip()
    if not texto:
        return None
    encontrada = _PREGUNTA.search(texto)
    if encontrada:
        return encontrada.group(0).strip()
    return None


def comentar_post(ig_media_id: str, caption: str) -> tuple[bool, str]:
    """Publica el primer comentario en un post recién publicado.

    Best-effort de principio a fin: si falla, el post ya está publicado y no se
    toca. Un comentario que no sale no puede tumbar una publicación buena.
    """
    texto = primer_comentario(caption)
    if not texto:
        return False, "el caption no lleva pregunta: no se autocomenta"
    comentario_id, msg = graph_api.comment_on_media(ig_media_id, texto)
    if comentario_id:
        logger.info("[IG] hilo arrancado en %s: %s", ig_media_id, texto[:60])
        return True, texto
    logger.warning("[IG] no se pudo autocomentar %s: %s", ig_media_id, msg)
    return False, msg


def comentarios_sin_responder(
    ig_media_id: str, nuestro_usuario: str = "entreinterioresrobe"
) -> list[dict]:
    """Comentarios de otros que aún no tienen respuesta.

    Para la bandeja del panel: en el nicho, las cuentas que contestan son las
    que tienen conversación de verdad y no un buzón de emojis.
    """
    comentarios, msg = graph_api.list_comments(ig_media_id)
    if not comentarios:
        if msg != "OK":
            logger.warning("[IG] no se pudieron leer comentarios: %s", msg)
        return []
    return [
        c for c in comentarios
        if c.get("username") != nuestro_usuario
        and not (c.get("replies") or {}).get("data")
    ]
