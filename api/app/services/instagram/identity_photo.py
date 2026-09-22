"""La foto de una entidad YA IDENTIFICADA, y solo si su procedencia la acredita.

Sustituye a `photo_finder.find` en el único camino de noticias (`publisher`), y
deja aquel intacto para el evergreen y el blog.

Qué hacía el de antes, y por qué salió lo que salió: pedía al LLM una frase de
búsqueda a partir del titular, se la pasaba a Google Images y elegía uno de los
quince primeros por `md5(título) % len(pool)`. Sin mirar el resultado — ni
siquiera el campo `title`, que la API sí devuelve. Con un titular que decía solo
«Guardiola» y un prompt que ordenaba «añade SIEMPRE contexto», la frase que salió
fue «Guardiola entrenador de fútbol», y el dado cayó en una foto de Pep.

El orden de aquí sale del principio del proyecto —una foto solo se publica si su
PROCEDENCIA acredita a quién retrata— así que va de más acreditado a menos:

  1. La ficha propia. Ya pasó `verify_provenance` en el cron de las 04:40 y ya
     se ve en la web pública.
  2. La P18 de Wikidata del QID que resolvimos, contra Commons. Es doble gate y
     entero determinista: la foto sale de la propia entidad, y Commons la
     corrobora por sus categorías, que son de otra mano.
  3. Google Images, con la consulta construida desde la entidad (nunca la
     adivinada por el modelo), dos filtros por delante y un gate de visión.
  4. Nada: arte propio. `imaging` ya cae solo, y no afirma identidad de nadie.

`photo_finder._wikidata_photo` ya hacía casi lo del paso 2, pero estaba enterrado
en el tercer respaldo, al que solo se llegaba si DataForSEO no respondía. O sea:
en operación normal, nunca.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

from app.services import identity_guard, image_guard
from app.services import news_entities as ne

logger = logging.getLogger(__name__)

# De dónde salió la foto, para que el panel lo enseñe.
FICHA = "ficha_propia"
COMMONS = "wikidata_p18"
GOOGLE = "google_images"
# No hay foto acreditada: el post va con arte propio, que no afirma la identidad
# de nadie. Es una constante y no un literal suelto porque el panel la lee para
# pintar su badge (`etiquetaFoto` en InstagramPlanner.tsx), y dos copias de una
# cadena en dos lenguajes distintos se desincronizan calladas.
ARTE_PROPIO = "arte_propio"


@dataclass(frozen=True)
class PhotoPick:
    url: str
    source: str
    verdict: str
    reason: str
    credit: str = ""
    thumb: str = ""
    query: str = ""
    page_url: str = ""
    site: str = ""
    needs_human: bool = False
    evidence: list[str] = field(default_factory=list)


def _terminos_esperados(entity: ne.ResolvedEntity) -> str:
    """Lo que sabemos de la entidad, para cotejarlo con lo que diga la foto."""
    return " ".join(p for p in (entity.label, entity.description) if p)


def _consulta(entity: ne.ResolvedEntity) -> str:
    """La búsqueda se CONSTRUYE desde la entidad resuelta, no se adivina."""
    partes = [entity.label or entity.mention.surface]
    if entity.description:
        partes.append(entity.description)
    return " ".join(partes).strip()


def _casa_el_candidato(cand: dict, entity: ne.ResolvedEntity) -> bool:
    """Filtro determinista y gratis, antes de gastar una llamada de visión.

    Exige las dos cosas: que el nombre aparezca en el texto que acompaña al
    resultado, y que aparezca algún término que distinga a ESTA entidad de sus
    homónimos. Con «Guardiola» solo, la primera condición la cumple también el
    entrenador; es la segunda la que lo deja fuera.
    """
    texto = image_guard._norm(
        " ".join([cand.get("title", ""), cand.get("page_url", ""), cand.get("site", "")])
    )
    if not texto.strip():
        return False

    nombre = image_guard._significant_words(entity.label or entity.mention.surface)
    if not nombre or not all(w in texto for w in nombre):
        return False

    discriminantes = image_guard._significant_words(entity.description or "")
    if not discriminantes:
        return True  # sin descripción no hay más que exigir
    return any(w in texto for w in discriminantes)


def _de_la_ficha(entity: ne.ResolvedEntity) -> PhotoPick | None:
    if entity.status != ne.CORPUS or not entity.image_url:
        return None
    return PhotoPick(
        url=entity.image_url,
        source=FICHA,
        verdict="accredited",
        reason="Foto de su ficha en el sitio, ya verificada por el cron de imágenes.",
    )


def _de_commons(entity: ne.ResolvedEntity) -> PhotoPick | None:
    if not entity.qid:
        return None
    from app.services import wikimedia
    from app.services.instagram.photo_finder import _p18_filename

    fichero = _p18_filename(entity.qid)
    if not fichero:
        return None
    info = wikimedia.get_file_info(fichero)
    if not info or not info.thumb_url:
        return None

    veredicto = image_guard.verify_provenance(
        entity_name=entity.label or entity.mention.surface,
        aliases=entity.aliases,
        image_url=info.thumb_url,
        source_url=f"https://commons.wikimedia.org/wiki/File:{fichero}",
        attribution=info.author,
        license_=info.license_short,
        expected_terms=_terminos_esperados(entity),
    )
    if not veredicto.publishable:
        logger.info(
            "[foto] Commons no acredita a %s: %s", entity.label, veredicto.reason
        )
        return None

    credito = (
        f"{info.author or 'Autor desconocido'} · Wikimedia Commons "
        f"({info.license_short or 'CC'})"
    )
    return PhotoPick(
        url=info.thumb_url,
        source=COMMONS,
        verdict=veredicto.status,
        reason=veredicto.reason,
        credit=credito,
        evidence=list(veredicto.evidence or []),
    )


def _de_google(
    entity: ne.ResolvedEntity, topic: dict, exclude: set[str]
) -> PhotoPick | None:
    from app.services.instagram import web_image

    consulta = _consulta(entity)
    candidatos = [
        c for c in web_image.search(consulta)
        if c.get("url") and c["url"] not in exclude
    ]
    encajan = [c for c in candidatos if _casa_el_candidato(c, entity)]
    logger.info(
        "[foto] «%s»: %d resultados, %d encajan con la entidad",
        consulta, len(candidatos), len(encajan),
    )
    if not encajan:
        return None

    # Rotación determinista ENTRE LOS QUE YA HAN PASADO el filtro. Antes se
    # rotaba entre los quince primeros sin filtrar, que es lo mismo que elegir al
    # azar entre aciertos y errores.
    semilla = int(hashlib.md5((topic.get("title") or "x").encode()).hexdigest(), 16)
    referencia = _referencia(entity)
    for i in range(len(encajan)):
        cand = encajan[(semilla + i) % len(encajan)]
        veredicto = identity_guard.verify_identity(
            cand["url"],
            label=entity.label or entity.mention.surface,
            description=entity.description or "",
            reference_url=referencia,
        )
        if veredicto.ok:
            return PhotoPick(
                url=cand["url"],
                thumb=cand.get("thumb", ""),
                source=GOOGLE,
                verdict="identidad_ok" if veredicto.checked else "identidad_sin_mirar",
                reason=veredicto.reason,
                query=consulta,
                page_url=cand.get("page_url", ""),
                site=cand.get("site", ""),
                needs_human=veredicto.needs_human,
            )
        logger.info("[foto] descartada %s: %s", cand["url"][:60], veredicto.reason)
    return None


def _referencia(entity: ne.ResolvedEntity) -> str | None:
    """Foto de referencia para comparar caras, si la entidad tiene una fiable."""
    if entity.image_url:
        return entity.image_url
    if not entity.qid:
        return None
    try:
        from app.services import wikimedia
        from app.services.instagram.photo_finder import _p18_filename

        fichero = _p18_filename(entity.qid)
        info = wikimedia.get_file_info(fichero) if fichero else None
        return info.thumb_url if info else None
    except Exception:  # noqa: BLE001
        return None


def find_for_entity(
    entity: ne.ResolvedEntity, topic: dict, exclude: set[str] | None = None
) -> PhotoPick | None:
    """Foto acreditada de la entidad, o None (y entonces: arte propio).

    Una entidad sin identificar no llega hasta aquí, y si llegara no daría foto:
    es la regla dura. Publicar una foto de alguien de quien no sabemos quién es
    no es un riesgo menor por ser una foto bonita.
    """
    if entity is None or not entity.da_foto:
        # Ojo al matiz: NO es `silenciada`. Una entidad que el artículo describe
        # («Moisés, concursante riojano») sí se puede nombrar, pero no se le sale
        # a buscar la cara por internet — ahí es donde se coló la de Pep.
        logger.info("[foto] sin identidad acreditada: no se busca foto.")
        return None

    exclude = exclude or set()
    elegida = _de_la_ficha(entity)
    if elegida is None:
        elegida = _de_commons(entity)
    if elegida is None:
        elegida = _de_google(entity, topic, exclude)

    if elegida is None:
        logger.info("[foto] nada acreditado para %s: irá arte propio.", entity.label)
    else:
        logger.info(
            "[foto] %s -> %s (%s)", entity.label, elegida.source, elegida.verdict
        )
    return elegida
