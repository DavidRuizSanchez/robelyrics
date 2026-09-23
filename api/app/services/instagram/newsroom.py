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
# Un intento más cuando lo ÚNICO que falla es el estilo. No es aflojar el
# listón: el listón es el mismo, lo que cambia es que a un «no escribas "la
# esencia de Robe"» se le puede hacer caso, y a un «no inventes una relación»
# el modelo ya demostró que no. Medido: una noticia legítima (el Sinfónico
# Extremo de Béjar) se caía con dos intentos, uno por fórmula de relleno y otro
# por fórmula de molde, y no tenía nada malo que contar.
MAX_REINTENTOS_ESTILO = 2


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

    # `silenciada`, no «no resuelta»: una persona corriente a la que el artículo
    # identifica («Moisés, concursante riojano») no tumba la noticia — no está en
    # Wikidata ni va a estarlo. Lo que la tumba es un nombre del que NI EL
    # ARTÍCULO dice quién es, que es con el que se confunde a un homónimo famoso.
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
    solo_texto = [n for n in ne.sin_foto(entidades) if n not in silenciadas]
    if solo_texto:
        logger.info("[redaccion] se nombran pero no dan foto: %s", ", ".join(solo_texto))
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


def texto_publicado(topic: dict) -> str:
    """TODO lo que hemos escrito nosotros y va a ver la gente.

    Antes esto era `headline + caption_body` y nada más, así que las SLIDES del
    carrusel —que se planifican después, en `publisher`— no pasaban por ninguna
    guarda. Mientras las slides eran un `re.split()` del caption daba igual: el
    texto ya estaba revisado. En cuanto alguien las ESCRIBE, es texto nuevo, y
    texto nuevo sin gate es exactamente por donde entró el post de Guardiola.
    """
    partes = [topic.get("headline") or "", topic.get("caption_body") or ""]
    partes += [(s.get("text") or "") for s in (topic.get("slides") or [])]
    partes.append(topic.get("cierre") or "")
    # Y la pregunta de cierre, por lo mismo: es la última línea del caption y la
    # escribimos nosotros. Mientras la ponía una plantilla después del gate, una
    # fórmula que el linter tenía vetada salía publicada igual.
    partes.append(topic.get("pregunta") or "")
    return "\n".join(p for p in partes if p.strip())


def escribir(
    db, topic: dict, entidades: list[ne.ResolvedEntity] | None = None,
    *, material: str | None = None, verificar_rel: bool = True,
    material_verificable: str | None = None,
) -> list[str]:
    """Escribe el post y no lo da por bueno hasta que pasa las guardas.

    Devuelve los avisos para el panel. Reescribe UNA vez diciéndole qué falló;
    si vuelve a fallar, el post no sale.

    `material` por defecto es el artículo de la noticia. Los evergreen y el blog
    pasan el suyo (el corpus propio) y `verificar_rel=False`: ver `caption_guard`.
    """
    from app.services.instagram import caption_guard, editorial, tono_guard

    entidades = entidades or []
    topic["entidades"] = entidades
    if material is None:
        material = topic.get("material") or ""
    avisos: list[str] = []
    veredicto = None
    intento = -1
    tope = MAX_REINTENTOS

    while intento < tope:
        intento += 1
        topic.pop("caption_body", None)
        topic.pop("headline", None)
        topic.pop("slides", None)
        topic.pop("cierre", None)
        topic.pop("pregunta", None)
        if veredicto is not None:
            # La reescritura sabe QUÉ falló: repetir la misma petición a ciegas
            # es tirar una moneda otra vez.
            topic["correcciones"] = veredicto.motivos
        editorial.enrich(topic)

        texto = texto_publicado(topic)
        veredicto = caption_guard.revisar(
            db, texto, material, entidades, verificar_rel=verificar_rel,
            material_verificable=material_verificable,
        )
        # ¿Es verdad? lo decide `caption_guard`. ¿Merece leerse? esto. Un post
        # puede pasar lo primero y seguir siendo humo, que es lo que pasaba.
        tono = tono_guard.revisar(
            titular=topic.get("headline") or "",
            comentario=topic.get("caption_body") or "",
            slides=topic.get("slides") or [],
            cierre=topic.get("cierre") or "",
            pregunta=topic.get("pregunta") or "",
        )
        veredicto.estilo.extend(tono.bloqueos)
        veredicto.avisos.extend(tono.avisos)
        topic["claims"] = veredicto.claims
        avisos = list(veredicto.avisos)

        if veredicto.ok:
            if intento:
                avisos.append(
                    f"El texto se reescribió {intento} vez/veces: el primero no "
                    "pasó las guardas."
                )
            return avisos

        if not veredicto.bloqueos:
            tope = MAX_REINTENTOS_ESTILO

        logger.warning(
            "[redaccion] intento %d rechazado: %s",
            intento + 1, " · ".join(veredicto.motivos),
        )

    raise TextoNoPublicable(
        "El texto no pasa las guardas después de reescribirlo: "
        + " · ".join(veredicto.motivos)
    )
