"""Lo que el post tiene DETRÁS, reunido y atribuido, antes de escribirlo.

El camino de Instagram escribía con lo que traía el tema y nada más: el
artículo en las noticias, y en los evergreen ni eso. Todo lo que el sitio sabe
—las letras, las entrevistas de Robe, las anotaciones de Genius, los dossieres
de entidad que alimentan las fichas SEO— estaba a una llamada de distancia y no
se usaba. De ahí salían las slides que valían para cualquier post.

Aquí se reúne ese material y se devuelve LISTO PARA EL PROMPT, con la
atribución pegada delante de cada pasaje (`corpus_for_queries.bloque_material`),
que es la forma de que al escribir no se pueda separar el dato de quién lo dijo.

Nada de esto inventa: si no hay material, se devuelve "" y quien llama decide.
Un post sin material se escribe con menos, no con relleno.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Cuántos pasajes del corpus entran. Pocos y buenos: el modelo tiene que poder
# leerlos enteros, y un caption son cuatro frases.
MAX_PASAJES = 4
# Tope del dossier de entidad. `entity_dossiers` está dimensionado para un
# artículo del blog (6.000 caracteres por canción); aquí sobra con el arranque,
# que es donde viven los datos duros (año, disco, créditos).
MAX_DOSSIER_CHARS = 2500


@dataclass
class Material:
    """Lo que hay detrás del post, en dos montones que NO son lo mismo.

    - `prompt`: todo, con su atribución, para ESCRIBIR.
    - `verificable`: solo lo de casa (nuestras propias fichas), para las
      guardas que tienen que decidir si una afirmación está respaldada.

    La distinción no es cosmética. El corpus trae análisis de terceros y
    transcripciones automáticas con erratas: son buen material para escribir
    citándolos, y son una fuente pésima para dar por buena una relación nueva
    («X es fan de Extremoduro»). La regla del 23-09 vale igual aquí: para
    AFIRMAR algo nuevo, la ausencia de evidencia bloquea.
    """

    prompt: str = ""
    verificable: str = ""

    def __bool__(self) -> bool:
        return bool(self.prompt)


def consultas_para(topic: dict, entidades: list | None = None) -> list[str]:
    """Qué le preguntamos al corpus para este post.

    No es el titular a secas: el titular es lo que dice el medio, y el corpus
    responde por CANCIÓN, DISCO o PERSONA. Una noticia sobre un bar de Bilbao no
    devuelve nada; «Calle Esperanza S/N», la canción de la que iba, devuelve su
    letra, sus créditos y su disco.
    """
    corpus = topic.get("corpus") or {}
    fuera: list[str] = []

    song = (corpus.get("song") or "").strip()
    album = (corpus.get("album") or "").strip()
    artist = (corpus.get("artist") or "").strip()
    person = (corpus.get("person") or "").strip()

    if song:
        fuera.append(f"«{song}» {artist} significado de la letra".strip())
        if album:
            fuera.append(f"{song} {album} grabación")
    elif album:
        fuera.append(f"{album} {artist} disco cómo se grabó".strip())
    if person:
        fuera.append(f"{person} Extremoduro Robe")

    titulo = (topic.get("title") or "").strip()
    if titulo:
        fuera.append(titulo)

    # Las entidades que el artículo identifica: son de quien va la noticia, y el
    # corpus puede tener material sobre ellas aunque el titular no lo sugiera.
    for e in (entidades or [])[:2]:
        label = (getattr(e, "label", "") or "").strip()
        if label and label.lower() not in titulo.lower():
            fuera.append(f"{label} Extremoduro")

    # Sin duplicados y sin perder el orden (el primero es el más específico).
    vistas: set[str] = set()
    limpias: list[str] = []
    for c in fuera:
        c = c.strip()
        clave = c.lower()
        if c and clave not in vistas:
            vistas.add(clave)
            limpias.append(c)
    return limpias[:3]


def reunir(db, topic: dict, *, entidades: list | None = None) -> Material:
    """Material del corpus para este post, ya atribuido.

    Dos fuentes que se suman, como en el blog:
      1. Los pasajes que responden a lo que el post trata (`corpus_for_queries`),
         que llegan con su atribución obligatoria.
      2. El dossier de las entidades del catálogo que el texto menciona
         (`news_research.entity_dossiers`): datos duros de casa (año, disco,
         créditos), no interpretación.
    """
    from app.services import corpus_for_queries

    trozos: list[str] = []

    # Los datos de casa van PRIMERO, para que sobrevivan al recorte del prompt:
    # es el mismo criterio que `entity_dossiers` aplica con sus `hard_facts`.
    dossier = _dossier(db, topic)
    if dossier:
        trozos.append(dossier)

    consultas = consultas_para(topic, entidades)
    if consultas:
        try:
            pasajes = corpus_for_queries.material_para_consultas(
                db, consultas, max_pasajes=MAX_PASAJES
            )
            bloque = corpus_for_queries.bloque_material(pasajes)
            if bloque:
                trozos.append(bloque)
        except Exception as exc:  # noqa: BLE001
            # El corpus es un extra: si Qdrant no responde, el post sale igual
            # con el material que ya tenía.
            logger.warning("[ig-material] corpus no disponible: %s", exc)

    return Material(prompt="\n\n----\n\n".join(trozos), verificable=dossier)


def _dossier(db, topic: dict) -> str:
    """Datos duros de las canciones/discos del catálogo que el texto menciona."""
    from app.services import news_research

    blob = " ".join(
        str(topic.get(k) or "")
        for k in ("title", "summary", "caption_body", "material")
    ).strip()
    if not blob:
        return ""
    try:
        texto = news_research.entity_dossiers(db, blob, max_songs=1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ig-material] dossier no disponible: %s", exc)
        return ""
    texto = (texto or "").strip()
    if not texto:
        return ""
    return (
        "DATOS DE CASA (de nuestras propias fichas; son verificados, úsalos "
        "sin atribuir):\n" + texto[:MAX_DOSSIER_CHARS]
    )
