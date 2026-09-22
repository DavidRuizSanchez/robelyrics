"""Redacción de un post de noticia: primero se sabe de quién se habla.

Orquesta el tramo que en el item 348 no existía: resolver las entidades del
artículo ANTES de escribir, aplicar la regla dura sobre lo que no se identifica,
y comprobar DESPUÉS y por texto que el caption la respeta.

La regla dura, y las dos formas que toma:

  - Si la entidad que NO se identifica es el sujeto de la noticia, no hay post.
    No se escribe sobre alguien de quien no sabemos quién es.
  - Si es una mención secundaria, el post sale pero esa entidad queda SILENCIADA:
    su nombre no puede aparecer en el texto, ni dar hashtag, ni dar foto.

Lo segundo no se le pide al modelo y ya está: se comprueba después buscando el
nombre en el caption. Es determinista, no cuesta un céntimo, no necesita red ni
clave de API, y es la comprobación que habría parado el incidente.
"""
from __future__ import annotations

import logging
import re

from app.services import news_entities as ne
from app.services.image_guard import _norm

logger = logging.getLogger(__name__)

MAX_REINTENTOS = 1


class SujetoNoIdentificado(RuntimeError):
    """No sabemos de quién habla la noticia, así que no se escribe sobre ella.

    El caso exacto: un titular que dice «Guardiola» y nada más. Wikidata, con ese
    nombre pelado, devuelve un apellido, un género de plantas y tres pueblos —
    ninguna persona. Elegir «el más probable» de esa lista es cómo se publican
    fotos del entrenador del Manchester City en una cuenta sobre Extremoduro.
    """


def resolver_entidades(db, topic: dict) -> list[ne.ResolvedEntity]:
    """Identifica a quién nombra el artículo y aplica la regla del sujeto."""
    entidades = ne.resolve_all(db, topic.get("material") or "", topic.get("title") or "")

    sujetos_perdidos = [
        e for e in entidades if e.mention.es_sujeto and e.silenciada
    ]
    # Un sujeto sin identificar tumba el post SOLO si no queda ningún otro sujeto
    # identificado: una noticia puede tener varios protagonistas (el acto, el
    # lugar, la persona) y perder uno secundario no la deja sin tema.
    if sujetos_perdidos and not any(
        e.mention.es_sujeto and e.resuelta for e in entidades
    ):
        primero = sujetos_perdidos[0]
        raise SujetoNoIdentificado(
            f"No se ha podido identificar a «{primero.mention.surface}», que es de "
            f"quien va la noticia: {primero.reason}"
        )

    silenciadas = ne.silenciadas(entidades)
    if silenciadas:
        logger.info("[redaccion] silenciadas (no se nombran): %s", ", ".join(silenciadas))
    return entidades


def _aparece(nombre: str, texto: str) -> bool:
    """¿Está este nombre en el texto? Con fronteras de palabra y sin tildes.

    Sin fronteras, «Robe» casaría dentro de «Robert» y silenciaríamos media
    Wikipedia; sin normalizar, «María» no casaría con «Maria».
    """
    palabras = [re.escape(w) for w in _norm(nombre).split() if len(w) > 2]
    if not palabras:
        return False
    patron = r"\b" + r"\s+".join(palabras) + r"\b"
    return re.search(patron, _norm(texto)) is not None


def comprobar_silenciadas(texto: str, entidades: list[ne.ResolvedEntity]) -> list[str]:
    """Nombres sin identificar que se han colado en el texto. Determinista."""
    return [n for n in ne.silenciadas(entidades) if _aparece(n, texto)]


class TextoNoPublicable(RuntimeError):
    """El texto no pasa las guardas ni después de reescribirlo.

    Insistir más sería confiar en que el modelo acabe obedeciendo, que es justo
    lo que no funcionó: el prompt del item 348 ya decía «no inventes ni un solo
    dato» y aun así inventó una afinidad entera.
    """


def escribir(db, topic: dict, entidades: list[ne.ResolvedEntity]) -> list[str]:
    """Escribe el caption y no lo da por bueno hasta que pasa las guardas.

    Devuelve los avisos para el panel. Reescribe UNA vez diciéndole qué falló;
    si vuelve a fallar, el post no sale.
    """
    from app.services.instagram import caption_guard, editorial

    topic["entidades"] = entidades
    material = topic.get("material") or ""
    avisos: list[str] = []
    veredicto = None

    for intento in range(MAX_REINTENTOS + 1):
        topic.pop("caption_body", None)
        topic.pop("headline", None)
        if veredicto is not None:
            # La reescritura sabe QUÉ falló: repetir la misma petición a ciegas
            # es tirar una moneda otra vez.
            topic["correcciones"] = list(veredicto.bloqueos)
        editorial.enrich(topic)

        texto = f"{topic.get('headline', '')}\n{topic.get('caption_body', '')}"
        veredicto = caption_guard.revisar(db, texto, material, entidades)
        topic["claims"] = veredicto.claims
        avisos = list(veredicto.avisos)

        if veredicto.ok:
            if intento:
                avisos.append("El texto se reescribió una vez: el primero no pasó las guardas.")
            return avisos

        logger.warning(
            "[redaccion] intento %d rechazado: %s",
            intento + 1, " · ".join(veredicto.bloqueos),
        )

    raise TextoNoPublicable(
        "El texto no pasa las guardas después de reescribirlo: "
        + " · ".join(veredicto.bloqueos)
    )
