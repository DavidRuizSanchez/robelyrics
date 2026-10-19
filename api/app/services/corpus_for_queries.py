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
- **No presta voz a nadie, ni se la da.** Hasta el 19-10-2026 el material de terceros
  se citaba atribuido («Manolillo Chinato contó que…»), y el primer borrador de una
  fusión salió lleno de «el blog javitojavierito recoge…» y «el análisis de Juancares
  en YouTube…». Criterio de David: el texto es NUESTRO. Lo ajeno es FONDO: orienta qué
  contar, nunca se nombra, y un dato que solo trae un tercero no se afirma salvo que
  se corrobore (`corroborar`). Solo Robe se cita, y con el medio donde lo dijo.
"""
from __future__ import annotations

import logging
import re
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


def bloque_material(pasajes: list[dict], verificados: list[str] | None = None) -> str:
    """El material, listo para el prompt, separado en lo que se AFIRMA y lo que no.

    - Lo que dijo Robe: se puede citar entre comillas y nombrando el medio.
    - Datos verificados: hechos de terceros que `corroborar` confirmó por otra vía.
    - Fondo: análisis, blogs, anotaciones, prensa. Orienta qué contar; ni se nombra
      ni se cita, y un dato que solo esté aquí no se escribe.
    """
    if not pasajes and not verificados:
        return ""
    robe, fondo = [], []
    for p in pasajes:
        frag = (p.get("fragmento") or "").strip()
        if p.get("kind") == "robe_interview":
            medio = (p.get("title") or "una entrevista").strip()
            robe.append(f"[LO QUE DIJO ROBE · {medio} — se puede citar con el medio]\n{frag}")
        else:
            fondo.append(f"[FONDO · responde a «{p.get('consulta', '')}»]\n{frag}")
    partes = []
    if robe:
        partes.append("PALABRAS DE ROBE (citables, con el medio):\n\n"
                      + "\n\n----\n\n".join(robe))
    if verificados:
        partes.append("DATOS VERIFICADOS (contrastados por otra vía; se pueden afirmar "
                      "en nuestra voz, sin decir de dónde salen):\n"
                      + "\n".join(f"- {v}" for v in verificados))
    if fondo:
        partes.append(
            "FONDO (de terceros: úsalo SOLO para saber de qué hablar. PROHIBIDO nombrar "
            "o citar a su autor, blog, canal o medio, y PROHIBIDO afirmar un dato que "
            "solo esté aquí; sus opiniones e hipótesis no son hechos):\n\n"
            + "\n\n----\n\n".join(fondo))
    return "\n\n====\n\n".join(partes)


# Cabeceras de bloque de `deep_research` que son de TERCEROS (ver `_source_head`).
_FONDO_RE = re.compile(
    r"^\[(?:TRANSCRIPCI[OÓ]N|youtube|blog|forum|foro|reddit|genius|prensa|press|fuente"
    r"|book|thesis|interview|about_robe|directo|concierto)\b", re.I)


def separar_material(material: str) -> tuple[str, str]:
    """(propio, fondo) de un dossier de `deep_research`.

    Propio: letra, créditos, hechos duros, la biografía autorizada, lo verificado
    externamente, versos, el grafo, el consenso destilado y la voz de Robe. Fondo:
    transcripciones, blogs, foros, anotaciones y prensa.
    """
    propio, fondo = [], []
    for bloque in (material or "").split("\n\n----\n\n"):
        if not bloque.strip():
            continue
        (fondo if _FONDO_RE.match(bloque.lstrip()) else propio).append(bloque)
    return "\n\n----\n\n".join(propio), "\n\n----\n\n".join(fondo)


_HECHO_SOBRE_EL_TEXTO = re.compile(
    r"\b(?:en el|del|según el) (?:texto|material|fragmento|art[ií]culo|an[aá]lisis)\b"
    r"|\bcitad[ao]s? en\b|\bse menciona\b|\bse cita\b", re.I)
_CUALITATIVO = re.compile(
    r"\b(?:[uú]nic[oa]s?|siempre|nunca|jam[aá]s|el mejor|la mejor|el m[aá]s|la m[aá]s"
    r"|estable|principal|clave|fundamental|legendari[oa]|m[ií]tic[oa]|todos|ninguno)\b",
    re.I)


def corroborar(client, fondo: str, propio: str, consultas: list[str], *,
               max_hechos: int = 6) -> tuple[list[str], list[str]]:
    """Qué datos del fondo se pueden afirmar: (verificados, descartados).

    Criterio de David (19-10-2026): un dato que solo trae un tercero («la tocaron por
    última vez el 13-11-2004 en Salamanca», de un análisis de YouTube) se escribe solo
    si se corrobora. Primero contra lo propio (cifras y nombres propios presentes en
    nuestro material) y después contra la web (`web_verify.classify_fact`), sin
    aceptar como evidencia el mismo texto que lo afirmaba.
    """
    if not (fondo or "").strip():
        return [], []
    from app.services import seo_style
    from scripts.seo.generate_deep import _chat

    try:
        data = _chat(
            client,
            "Del texto de abajo, extrae como máximo "
            f"{max_hechos} HECHOS CONCRETOS y comprobables (fecha, lugar, nombre, cifra, "
            "título) que ayuden a responder: " + "; ".join(consultas) + ".\n"
            "Nada de opiniones, interpretaciones ni hipótesis («quizá», «parece», "
            "«se cree»). Cada hecho, una frase autónoma y sin decir de dónde sale.\n"
            f'TEXTO:\n"""{fondo[:8000]}"""\n'
            'Devuelve JSON {"hechos": ["..."]}.',
            max_tokens=700, temp=0.0,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[corroborar] extracción falló: %s", exc)
        return [], []
    hechos = [h.strip() for h in (data.get("hechos") or []) if isinstance(h, str) and h.strip()]
    permitidos = seo_style.tokens_permitidos(propio)
    verificados, descartados = [], []
    for h in hechos[:max_hechos]:
        # «En una formación citada en el texto…» no es un hecho: es el extractor
        # hablando del material (visto en /personas, 19-10-2026).
        if _HECHO_SOBRE_EL_TEXTO.search(h):
            descartados.append(h)
            continue
        # Contra lo propio solo vale un dato DATABLE (año, cifra) cuyos nombres y
        # cifras estén en nuestro material. Un juicio («Robe fue el único miembro
        # estable») pasaba igual —sus nombres están todos— y era falso.
        if (not _CUALITATIVO.search(h) and re.search(r"\d", h)
                and not seo_style.verify_no_invention(h, permitidos)):
            verificados.append(h)
            continue
        try:
            from app.services.web_verify import classify_fact

            v = classify_fact(h, query=h)
        except Exception:  # noqa: BLE001
            v = {}
        evidencia = (v.get("evidence") or "").lower()
        # La evidencia no puede ser el propio texto del que salió el dato.
        eco = evidencia and evidencia[:80] in (fondo or "").lower()
        if (v.get("verdict") or "").lower() == "supported" and not eco:
            verificados.append(h)
        else:
            descartados.append(h)
    return verificados, descartados


def parte_afirmable(bloque: str) -> str:
    """De un `bloque_material`, solo lo que se puede afirmar (Robe y verificados).

    Es lo que recibe el verificador: si ve el FONDO, da por bueno un dato que solo
    trae un tercero, que es justo lo que no se puede escribir.
    """
    return "\n\n".join(p for p in (bloque or "").split("\n\n====\n\n")
                        if not p.lstrip().startswith("FONDO"))
