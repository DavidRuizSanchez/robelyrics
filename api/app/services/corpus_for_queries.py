"""Material del corpus para responder a una CONSULTA concreta.

(El nombre `seo_research` ya estaba cogido por el wrapper de DataForSEO
del blog; esto es otra cosa: no busca keywords, busca RESPUESTAS.)

Hasta ahora todo el motor de contenido recuperaba material **por entidad**: el
dossier de `deep_research.gather_entity_dossier` ni siquiera acepta una consulta, y
su vector de búsqueda es el del nombre del sujeto (`deep_research.py:385`). Con eso
basta para escribir una ficha de cero, pero no para optimizar una que ya existe:
ahí la pregunta no es «qué se sabe de Guerrero» sino «qué significa *como buen
guerrero solo tengo miedo*», que es lo que la gente escribe en Google.

El resultado de esa asimetría, medido el 22-09-2026: las ampliaciones se llenaban de
«lucha interna» y «resistencia emocional» y el gate las tumbaba con razón, mientras
el corpus tenía guardado, sin que nadie lo mirara, lo que respondía de verdad:

  - «ama ama y ensancha el alma significado» → una anotación de Genius que explica la
    estrofa y una entrevista a **Manolillo Chinato**, el autor del poema.
  - «donde se rompen las olas significado» → un directo de Juancares sobre el tema.
  - «qué significa rock transgresivo» → dos análisis de Juancares.

Está todo vectorizado desde siempre. Solo faltaba preguntarle al corpus lo que le
pregunta la gente.

## Dos cosas que este módulo NO hace

- **No relaja nada.** Es la doctrina del proyecto aplicada al circuito SEO:
  «potenciar es traer MÁS MATERIAL REAL, nunca aflojar el listón». Lo que devuelve
  entra como material para escribir, y todas las verificaciones siguen igual.
- **No presta voz a nadie.** El material de terceros viaja con su autor y su tipo, y
  se cita atribuido —«Manolillo Chinato contó que…»— nunca como voz de Robe ni como
  verdad del sitio. Un análisis de Juancares no es algo que dijera Robe, y las
  transcripciones automáticas además traen erratas.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Suelo de parecido. La colección de interpretaciones se sirve a 0.35, pero a ese
# nivel entra ruido puro: buscando «como buen guerrero solo tengo miedo» salía a 0.48
# un corte de Las Mañanas de Radio Nacional que no habla de esto en absoluto. 0.45
# deja fuera ese tipo de vecino sin perder los hallazgos buenos (0.47-0.70).
MIN_SCORE = 0.45
# Pasajes que se le enseñan al motor. Más no es mejor: el detector de huecos solo
# puede proponer UNA sección por pasada.
MAX_PASAJES = 8

# La prensa comercial está fuera del corpus por decisión del proyecto, pero sus
# textos siguen indexados de cuando entraban.
_MEDIOS_VETADOS = ("mondosonoro.com", "efeeme.com", "rockdelux.com")

# Cómo se nombra a cada tipo de fuente cuando se cita. Sin entrada aquí, no se cita.
_ATRIBUCION = {
    "youtube_transcript": "análisis de {autor} en YouTube",
    "genius_annotation": "una anotación de Genius",
    "blog": "el blog {autor}",
    "prensa": "{autor}",
    "press": "{autor}",
    "interview": "una entrevista con {autor}",
    "robe_interview": "una entrevista con Robe",
    "about_robe": "{autor}",
}


def _embed(texto: str) -> list[float] | None:
    from app.services.embeddings import get_embedder

    try:
        emb = get_embedder()
        return emb.embed_one(texto) if hasattr(emb, "embed_one") else emb.embed([texto])[0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("[seo-research] no se pudo embeber «%s»: %s", texto[:40], exc)
        return None


def _es_utilizable(pasaje: dict, consulta: str) -> tuple[bool, str]:
    """Dos filtros que el umbral de parecido no cubre.

    **El veto de prensa**: Mondo Sonoro, Efe Eme y Rockdelux están fuera del corpus
    por decisión del proyecto, y sus textos siguen indexados de antes. Un pasaje de
    Rockdelux entró a 0.56 en la primera prueba.

    **El vecino semántico que no habla de esto**: buscando «donde se rompen las olas»
    salía a 0.54 un corte de Las Mañanas de Radio Nacional, y a 0.56 el menú de
    navegación de una web de conciertos. Se exige que el pasaje comparta al menos una
    palabra con la consulta que lo trajo: si no nombra nada de lo que se preguntaba,
    no lo responde por muy cerca que caiga en el espacio vectorial.
    """
    from app.services.seo_style import content_tokens, flatten

    url = (pasaje.get("url") or "").lower()
    if any(dom in url for dom in _MEDIOS_VETADOS):
        return False, "medio vetado"
    texto = flatten(pasaje.get("fragmento"))
    toks = [t for t in content_tokens(consulta) if len(t) > 3]
    if toks and not any(f" {t}" in texto for t in toks):
        return False, "no menciona nada de lo que se preguntaba"
    return True, ""


def atribucion(pasaje: dict) -> str | None:
    """Cómo se nombra la fuente al citarla. `None` = no se puede citar."""
    plantilla = _ATRIBUCION.get((pasaje.get("kind") or "").strip())
    autor = (pasaje.get("author") or pasaje.get("titulo") or "").strip()
    if not plantilla:
        return None
    if "{autor}" in plantilla and not autor:
        return None
    return plantilla.format(autor=autor)


def material_para_consultas(
    db, consultas: list[str], *, k: int = 5, min_score: float = MIN_SCORE,
    max_pasajes: int = MAX_PASAJES,
) -> list[dict[str, Any]]:
    """Pasajes del corpus que responden a estas consultas, con su procedencia.

    Cada pasaje trae `fragmento`, `kind`, `author`, `title`, `url`, `score` y
    `atribucion` (cómo citarlo). Lo que no se puede atribuir se descarta: sin saber
    de quién es, no se publica.
    """
    from app.services import retrieval

    vistos: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for consulta in consultas:
        consulta = (consulta or "").strip()
        if not consulta:
            continue
        vec = _embed(consulta)
        if not vec:
            continue
        try:
            pasajes = retrieval.search_interpretations_passages(
                db, vec, k=k, score_threshold=min_score)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[seo-research] búsqueda falló: %s", exc)
            continue
        # La voz de Robe sobre el tema, que pesa más que cualquier análisis ajeno.
        try:
            for v in retrieval.search_robe_voice(vec, k=2, score_threshold=min_score):
                pasajes.append({"fragmento": v["fragmento"], "kind": "robe_interview",
                                "author": "Robe", "title": v.get("titulo"),
                                "url": v.get("url"), "score": v["score"],
                                "source_id": f"voice:{v.get('titulo')}", "chunk_index": 0})
        except Exception:  # noqa: BLE001
            pass
        for p in pasajes:
            clave = (p.get("source_id"), p.get("chunk_index"))
            if clave in vistos or not (p.get("fragmento") or "").strip():
                continue
            utilizable, motivo = _es_utilizable(p, consulta)
            if not utilizable:
                logger.debug("[seo-research] descartado (%s): %s", motivo,
                             (p.get("fragmento") or "")[:60])
                continue
            attr = atribucion(p)
            if not attr:
                continue
            vistos.add(clave)
            out.append({**p, "consulta": consulta, "atribucion": attr})
    out.sort(key=lambda p: -float(p.get("score") or 0))
    return out[:max_pasajes]


def bloque_material(pasajes: list[dict]) -> str:
    """El material, listo para el prompt, con la atribución pegada a cada pasaje.

    El formato importa: la atribución va DELANTE del texto, para que al escribir no
    se pueda separar el dato de quién lo dijo.
    """
    if not pasajes:
        return ""
    trozos = []
    for p in pasajes:
        es_robe = p.get("kind") == "robe_interview"
        cabecera = (
            "LO QUE DIJO ROBE" if es_robe
            else f"MATERIAL DE UN TERCERO — cítalo como «{p['atribucion']}»"
        )
        trozos.append(
            f"[{cabecera} · responde a «{p['consulta']}»]\n{p['fragmento'].strip()}"
        )
    return (
        "MATERIAL QUE RESPONDE A LO QUE LA GENTE BUSCA (úsalo con su atribución; lo "
        "de terceros NUNCA como voz de Robe ni como verdad del sitio):\n\n"
        + "\n\n----\n\n".join(trozos)
    )
