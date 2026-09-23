"""Redacción de un post de Instagram: caption, titular y SLIDES del carrusel.

Convierte el material REAL que hay detrás del post (el artículo de la noticia,
o el material del corpus en los evergreen) en el texto que se publica.

Dos cosas que antes no estaban y son el motivo de este fichero:

- **Las slides se redactan aquí.** Antes las "escribía" `carousel._frases`: un
  `re.split()` por puntos sobre el resumen, cogiendo las tres primeras frases de
  más de 40 caracteres. El carrusel no tenía autor, y por eso todos los posts
  sonaban igual.
- **La voz no se escribe en este fichero.** Sale de `voice.build_system_prompt`
  (`family="instagram"`), la misma que usan el blog, las fichas SEO y el
  consultorio. Tener aquí un system prompt propio —defensivo, sin una línea
  sobre quién lee ni sobre el tono— es lo que dejó a Instagram fuera de las
  reglas duras del sitio: la del nombre, la de la raya larga, la de no inventar.

Si OpenAI no está disponible se degrada con elegancia: el post sale con el texto
de partida y sin slides redactadas, y `carousel` vuelve a su troceo de siempre.
"""
from __future__ import annotations

import json
import logging
import os
import re

from openai import OpenAI, OpenAIError

from app.services import robe_quotes, voice
from app.services.instagram import tono_guard
from app.services.text_sanitizer import strip_ai_tells

logger = logging.getLogger(__name__)

# gpt-4o, no mini: aquí se decide el texto que ve la gente, y la diferencia
# entre los dos se nota justo en esto (no repetir el molde, no rellenar).
_MODEL = "gpt-4o"
# Tope del artículo que se le pasa al modelo.
MAX_MATERIAL_CHARS = 4000
# Tope del material del corpus (pasajes atribuidos). Va aparte del artículo:
# son dos fuentes distintas y se capan por separado.
MAX_CORPUS_CHARS = 6000

# Contrato de las slides. Los topes de longitud no se pueden expresar en el
# esquema (`maxLength` no entra en el subset de structured outputs), así que van
# en el prompt y se comprueban aquí al normalizar.
# Calibrados contra slides REALES, no a ojo. Con el mínimo en 70 se descartaba
# «Pablo Recuero Pérez dirige y arregla el espectáculo sinfónico» (62), que es
# exactamente el tipo de dato que se le pide al modelo; con el kicker en 14 se
# descartaba «SINFÓNICO EXTREMO» (17), que cabe de sobra en la tarjeta (`imaging`
# corta en 24 y la tira de mono a 15px ocupa un tercio del ancho).
SLIDE_MIN_CHARS = 55
SLIDE_MAX_CHARS = 210
KICKER_MAX_CHARS = 20
MAX_SLIDES = 3

# Evergreen: el contenido de partida (un verso, una cita de Robe, una efeméride)
# es AJENO o ya está verificado. Se comenta alrededor, no se reescribe.
TIPOS_TEXTO_INTOCABLE = ("quote", "robe_quote")


def enrich(topic: dict) -> None:
    """Añade al topic (in-place) el texto redactado del post.

    Claves que deja: `caption_body`, `headline`, `slides`, `cierre`,
    `image_query`, `image_search`, `hashtags`.
    """
    title = (topic.get("title") or "").strip()
    summary = (topic.get("summary") or "").strip()
    # El ARTÍCULO, no el extracto. El extracto venía vacío en el 83,5% de las
    # noticias (los feeds de Google News repiten el titular y el agregador lo
    # vacía), así que pedir «2 a 4 frases comentando la noticia» con eso delante
    # era pedir que rellenase. `topics._tema_de_noticia` lo trae de
    # `news_items.body_text`; sin él, `publisher.prepare` ni llega hasta aquí.
    material = (topic.get("material") or "").strip()
    # Material del corpus, ya atribuido por `instagram.material`. Es lo que
    # convierte un post correcto en uno que un fan quiere leer: la letra, lo que
    # dijo Robe, la anotación que explica la estrofa.
    corpus = (topic.get("material_corpus") or "").strip()
    content_type = topic.get("content_type") or "news"

    datos = _generate(
        title, summary, topic.get("category", ""), topic.get("tone", "neutral"),
        material=material, corpus=corpus, content_type=content_type,
        # `texto_base` lo pone quien llama con el texto DEFINITIVO del post
        # (la prosa del blog, el verso, la efeméride). No se lee de
        # `caption_body` porque el bucle de reescritura de `newsroom` lo vacía
        # en cada intento, y el segundo intento se quedaría sin texto de partida.
        texto_base=(topic.get("texto_base") or "").strip(),
        entidades=topic.get("entidades") or [],
        correcciones=topic.get("correcciones") or [],
    )
    if datos is None:
        # Degradación: el post sale igual, con el texto de partida.
        topic.setdefault("caption_body", _fallback_body(title, summary))
        topic.setdefault("headline", title)
        topic.setdefault("image_query", "")
        topic.setdefault("image_search", "")
        topic.setdefault("hashtags", [])
        return

    # El saneador corre sobre lo que escribimos NOSOTROS (el comentario, el
    # titular, las slides), nunca sobre el titular del medio ni sobre un verso:
    # lo ajeno se cita, no se reescribe. Entre otras cosas aplica la regla dura
    # del nombre — un caption publicado decía «Robe Iniesta».
    # El cuerpo del post del blog no se toca: es la prosa que ya escribió el
    # motor profundo, con sus gates detrás. Aquí solo se le añaden las slides.
    if content_type == "blog":
        topic["caption_body"] = (topic.get("texto_base") or "").strip() or _fallback_body(
            title, summary
        )
    else:
        topic["caption_body"] = strip_ai_tells(datos["comentario"]) or _fallback_body(
            title, summary
        )
    # El titular SOLO se escribe en las noticias. En un post de verso, la
    # tarjeta lleva el verso: dejar que el modelo le pusiera título daba
    # «Lágrimas Invisibles» encima de una letra de Robe, que es justo lo que no
    # puede pasar. En el blog el titular es el del post, que ya está pensado.
    if content_type == "news":
        topic["headline"] = strip_ai_tells(datos["titular"]) or title
    else:
        topic["headline"] = (topic.get("texto_base") or title).strip()
    topic["slides"] = _normalizar_slides(datos["slides"])
    topic["cierre"] = strip_ai_tells(datos["cierre"]) or ""
    # Nombre propio del SUJETO (para el hashtag #Sujeto).
    topic["image_query"] = datos["image_query"]
    # Query DESAMBIGUADA para buscar su foto en Google Images (con contexto,
    # para no traer homónimos). Vacío si el sujeto no es identificable.
    topic["image_search"] = datos["image_search"]
    # Hashtags específicos del contenido (#MilongasExtremas, etc.).
    topic["hashtags"] = datos["hashtags"]


def _fallback_body(title: str, summary: str) -> str:
    if summary and summary.lower() not in title.lower():
        return f"{title}\n\n{summary}"
    return title


def _persona(content_type: str) -> str:
    """Quién escribe.

    Las noticias van en tercera persona cálida (igual que el blog hace con
    ellas): el protagonista es el sujeto de la noticia, no el fan que la cuenta.
    Todo lo demás —versos, efemérides, anécdotas, citas— es material de casa y
    lo firma el megafan en primera persona.
    """
    return "tercera_calida" if content_type in ("news", "blog") else "primera_admirador"


def _esquema() -> dict:
    """Contrato tipado de la respuesta.

    Con `json_object` a pelo (lo de antes) el modelo devolvía lo que quería y el
    parseo era defensivo. Aquí las claves están garantizadas; lo que no se puede
    garantizar en el esquema (longitudes, número de slides) se pide en el prompt
    y se comprueba en `_normalizar_slides`.
    """
    return {
        "name": "post_instagram",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "comentario": {"type": "string"},
                "titular": {"type": "string"},
                "slides": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "kicker": {"type": "string"},
                            "text": {"type": "string"},
                        },
                        "required": ["kicker", "text"],
                    },
                },
                "cierre": {"type": "string"},
                "image_query": {"type": "string"},
                "image_search": {"type": "string"},
                "hashtags": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "comentario", "titular", "slides", "cierre",
                "image_query", "image_search", "hashtags",
            ],
        },
    }


def _normalizar_slides(raw: object) -> list[dict]:
    """Deja solo las slides que caben en la tarjeta y dicen algo.

    Una slide corta de más no se "arregla" recortando: se descarta. El carrusel
    sabe funcionar con dos slides, y una tarjeta con media frase se ve.
    """
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    vistos: set[str] = set()
    for s in raw:
        if not isinstance(s, dict):
            continue
        texto = strip_ai_tells((s.get("text") or "").strip()) or ""
        texto = re.sub(r"\s+", " ", texto).strip()
        kicker = re.sub(r"\s+", " ", (s.get("kicker") or "").strip()).upper()
        if not texto or len(texto) < SLIDE_MIN_CHARS or len(texto) > SLIDE_MAX_CHARS:
            # Se registra el motivo: un carrusel que se queda en dos tarjetas sin
            # que nadie sepa por qué es lo que hace imposible calibrar los topes.
            logger.info(
                "[editorial] slide descartada (%d caracteres): %s",
                len(texto), texto[:60],
            )
            continue
        if len(kicker) > KICKER_MAX_CHARS:
            logger.info("[editorial] slide descartada (kicker «%s»)", kicker)
            continue
        # Dos slides que dicen lo mismo son una slide y un hueco.
        huella = texto.lower()[:60]
        if huella in vistos:
            logger.info("[editorial] slide repetida: %s", texto[:60])
            continue
        vistos.add(huella)
        out.append({"kicker": kicker, "text": texto})
        if len(out) == MAX_SLIDES:
            break
    return out


def _generate(
    title: str, summary: str, category: str, tone: str = "neutral",
    *, material: str = "", corpus: str = "", content_type: str = "news",
    texto_base: str = "", entidades: list | None = None,
    correcciones: list[str] | None = None,
) -> dict | None:
    """Llama a OpenAI. Devuelve el dict con el texto, o None si no se pudo."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    # Solo la noticia parte de un artículo ajeno. El blog trae su propia prosa
    # (la escribió el motor profundo del sitio) y el evergreen sale del corpus:
    # en esos dos el texto de partida es MATERIAL, no algo que reescribir.
    es_noticia = content_type == "news"

    # En temas luctuosos/conmemorativos, el comentario y el titular deben ser
    # sobrios: ni efusividad, ni ganchos, ni titular "llamativo".
    if tone == "sober":
        nota_tono = (
            "TONO: este tema es luctuoso o conmemorativo (muerte, homenaje, "
            "reconocimiento póstumo). Trátalo con respeto y sobriedad, sin "
            "sensacionalismo, sin signos de exclamación y sin frivolidad."
        )
        nota_titular = (
            '  "titular": una frase corta y sobria (máximo 9 palabras), '
            "con mayúscula inicial y sin punto final."
        )
    else:
        nota_tono = ""
        nota_titular = (
            '  "titular": una frase corta y llamativa (máximo 9 palabras) para '
            "una tarjeta visual, con mayúscula inicial y sin punto final."
        )
    if not es_noticia:
        # La tarjeta de un evergreen lleva el verso o la efeméride, no un título
        # inventado. Se pide igual porque el esquema lo exige, y se ignora.
        nota_titular = (
            '  "titular": devuelve el texto de partida tal cual, sin cambiarlo '
            "(en este post no se usa)."
        )

    # El artículo se capa: lo que importa es que el modelo tenga los HECHOS, no
    # que pague por el pie de foto y los enlaces relacionados.
    cuerpo = material[:MAX_MATERIAL_CHARS] if material else ""
    if es_noticia:
        bloque_material = (
            f"ARTÍCULO (única fuente de hechos sobre la actualidad; no uses nada "
            f'que no esté aquí):\n"""\n{cuerpo}\n"""\n'
            if cuerpo
            else "ARTÍCULO: (no disponible)\n"
        )
    else:
        bloque_material = (
            f'TEXTO DEL POST (ya es definitivo, NO lo reescribas):\n"""\n'
            f'{texto_base or summary or title}\n"""\n'
        )
        if content_type in TIPOS_TEXTO_INTOCABLE:
            bloque_material += (
                "Ese texto es AJENO (un verso o una cita literal). No lo cambies "
                "ni una palabra, no lo parafrasees y no lo repitas entero en las "
                "slides: escribes ALREDEDOR de él.\n"
            )
    bloque_corpus = ""
    if corpus:
        bloque_corpus = (
            "MATERIAL DE CASA (letras, entrevistas, anotaciones y datos del "
            "corpus; lo de terceros va con su atribución y NUNCA como voz de "
            f"Robe):\n{corpus[:MAX_CORPUS_CHARS]}\n"
        )
    bloque_entidades = _bloque_entidades(entidades or [])
    bloque_correcciones = ""
    if correcciones:
        bloque_correcciones = (
            "TU VERSIÓN ANTERIOR SE RECHAZÓ POR ESTO. Corrígelo; no lo repitas:\n"
            + "\n".join(f"  · {c}" for c in correcciones)
            + "\n"
        )

    # Un clip de concierto va de UN MOMENTO concreto que se está viendo, no de
    # la canción en abstracto. Sin esto el modelo se pone a interpretar la letra
    # («refleja la lucha interna», «es un grito de desesperación»), que es humo
    # y encima no es lo que se ve en el vídeo.
    nota_comentario = (
        '  "comentario": de 2 a 4 frases comentando la noticia como Entre '
        "Interiores, sin mencionar ningún medio y sin inventar datos.\n"
        if es_noticia
        else '  "comentario": de 1 a 3 frases que AÑADAN algo que no esté ya en '
        "el texto del post, y que salga del material: de dónde sale, quién lo "
        "tocó, qué se dijo de esa canción, qué pasó al grabarla, con qué se "
        "conecta. Cada frase, con su dato. PROHIBIDO explicar lo que el texto ya "
        "dice, y prohibido interpretar al aire ('encapsula la esencia de', 'una "
        "oda a', 'habla de la soledad'): si el material no respalda una lectura, "
        "no la hagas. Si el material no da para nada de esto, escribe una sola "
        "frase con lo que el material SÍ dice. Si el post va de una canción "
        "concreta, habla de ELLA antes que del disco entero.\n"
    )

    # Un clip de concierto va de UN MOMENTO que se está viendo, no de la
    # canción en abstracto. Sin esto el modelo interpreta la letra («refleja la
    # lucha interna», «es un grito de desesperación»): humo, y encima no es lo
    # que se ve en el vídeo.
    if content_type == "clip":
        nota_comentario = (
            '  "comentario": de 1 a 3 frases sobre EL MOMENTO QUE SE VE en el '
            "clip y sobre el concierto: qué suena, en qué punto de la canción, "
            "y dónde y cuándo fue si consta. PROHIBIDO interpretar la letra o "
            "explicar de qué va la canción, que no es lo que se está viendo. Si "
            "no consta la fecha o el sitio, NO los menciones ni los aproximes.\n"
        )

    user = (
        f"Categoría: {category}\n"
        f"Tipo de post: {content_type}\n"
        f"Tema: {title}\n"
        f"Extracto disponible: {summary or '(sin extracto)'}\n"
        f"{bloque_material}"
        f"{bloque_corpus}"
        f"{bloque_entidades}"
        f"{bloque_correcciones}"
        f"{nota_tono}\n"
        f"{tono_guard.bloque_prohibidas()}\n\n"
        "Devuelve un objeto JSON con estas claves:\n"
        f"{nota_comentario}"
        f"{nota_titular}\n"
        f'  "slides": de 2 a {MAX_SLIDES} tarjetas para el carrusel. Cada una es '
        'un objeto {"kicker": …, "text": …}.\n'
        f"      · \"text\": entre {SLIDE_MIN_CHARS} y {SLIDE_MAX_CHARS} "
        "caracteres, UNA idea con UN dato concreto (un año, un título, un "
        "nombre, una cifra, un verso corto). Se lee sola, en la pantalla de un "
        "móvil, sin haber leído la anterior.\n"
        "      · Cada slide cubre un ÁNGULO distinto, no el mismo hecho con "
        "otras palabras. Los ángulos, por orden de preferencia: (1) lo que pasa "
        "en ESTA canción o en este hecho concreto; (2) quién estaba detrás "
        "(quién tocaba, quién produjo, quién lo escribió); (3) con qué se "
        "conecta en el resto de la obra o qué pasó después. Si dos tarjetas "
        "acaban diciendo lo mismo, borra una: una tarjeta de relleno se nota "
        "más que una tarjeta menos.\n"
        "      · Ninguna repite frases del comentario ni del titular.\n"
        f"      · \"kicker\": la etiqueta de arriba, máximo {KICKER_MAX_CHARS} "
        "caracteres, en mayúsculas, CONCRETA y distinta en cada slide (\"1997\", "
        "\"EL DISCO\", \"QUIÉN TOCA\", \"LA LETRA\"). Prohibido numerar "
        "(\"CLAVE 01\", \"PUNTO 2\"): eso no es una etiqueta, es un contador.\n"
        '  "cierre": una sola frase para la última tarjeta, que cierre ESTE post '
        "(no vale una frase intercambiable). Máximo 90 caracteres.\n"
        '  "image_query": el NOMBRE PROPIO del SUJETO que PROTAGONIZA el post '
        "(quien hace la acción: el grupo, artista, banda o lugar del "
        "que VA), para el hashtag. Si es un homenaje/tributo/versión, "
        "el sujeto es QUIEN HOMENAJEA, no Robe. Ej.: en 'Milongas Extremas "
        "homenajea a Robe' es 'Milongas Extremas'; en 'Leiva versiona a "
        "Extremoduro' es 'Leiva'. Si no hay sujeto claro pero va del universo "
        "Extremoduro/Robe, usa 'Extremoduro' o 'Robe' (NUNCA 'Robe Iniesta').\n"
        '  "image_search": una frase de búsqueda en Google Imágenes que '
        "identifique SIN AMBIGÜEDAD al sujeto en su contexto, para encontrar una "
        "foto CORRECTA. Añade SIEMPRE contexto (música, banda, grupo, cantante, "
        "Extremoduro, el programa/lugar...). Ej.: 'Milongas Extremas banda "
        "uruguaya', 'Leiva cantante músico', 'Roberto Iniesta Extremoduro', 'David "
        "Broncano La Revuelta'. MUY IMPORTANTE: si el sujeto es un apellido o "
        "nombre común y NO puedes identificarlo con seguridad (p.ej. 'Pérez' a "
        "secas), NO te inventes contexto: deja image_search VACÍO y usaremos una "
        "foto de Robe/Extremoduro. Mejor genérico-correcto que específico-falso.\n"
        '  "hashtags": lista de 1 a 3 hashtags en CamelCase, sin espacios y sin '
        "tildes, ESPECÍFICOS del contenido (nombres propios de grupos, "
        "personas, lugares o canciones citados). Ej.: [\"#MilongasExtremas\"], "
        '["#Leiva", "#PremiosDeLaMusica"]. NADA de genéricos (#Música, #Rock, '
        "#Extremoduro): esos ya se añaden aparte."
    )

    system = voice.build_system_prompt(
        family="instagram",
        persona=_persona(content_type),
        tone_quotes=robe_quotes.tone_quotes(k=3),
    )
    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.7,
            response_format={"type": "json_schema", "json_schema": _esquema()},
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        raw_tags = data.get("hashtags") or []
        if isinstance(raw_tags, str):
            raw_tags = [raw_tags]
        hashtags = [_clean_hashtag(t) for t in raw_tags]
        return {
            "comentario": (data.get("comentario") or "").strip(),
            "titular": (data.get("titular") or "").strip(),
            "slides": data.get("slides") or [],
            "cierre": (data.get("cierre") or "").strip(),
            "image_query": (data.get("image_query") or "").strip(),
            "image_search": (data.get("image_search") or "").strip(),
            "hashtags": [t for t in hashtags if t],
        }
    except (OpenAIError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("[editorial] OpenAI falló (%s); se usa el texto original.", exc)
        return None


def _bloque_entidades(entidades: list) -> str:
    """Quién es quién, y a quién NO se puede nombrar.

    Lo segundo no se deja al criterio del modelo: `newsroom` lo comprueba después
    buscando el nombre en el texto. Esto solo le ahorra el viaje.
    """
    if not entidades:
        return ""
    lineas = []
    identificadas = [e for e in entidades if getattr(e, "resuelta", False)]
    silenciadas = [e for e in entidades if not getattr(e, "resuelta", False)]
    if identificadas:
        lineas.append("QUIÉN ES QUIÉN (identificado; usa estos nombres y cargos):")
        for e in identificadas:
            desc = f" — {e.description}" if e.description else ""
            lineas.append(f"  · {e.label}{desc}")
    if silenciadas:
        lineas.append(
            "NO NOMBRAR (no hemos podido identificar a quién se refiere el artículo; "
            "no los menciones, ni por su nombre ni por su cargo, y no digas nada "
            "sobre ellos):"
        )
        lineas.extend(f"  · {e.mention.surface}" for e in silenciadas)
    return "\n".join(lineas) + "\n"


def _clean_hashtag(tag: str) -> str:
    """Normaliza un hashtag del LLM: garantiza '#', CamelCase y sin espacios."""
    raw = (tag or "").strip().lstrip("#")
    raw = re.sub(r"[^\w\s]", "", raw, flags=re.UNICODE).strip()
    if not raw:
        return ""
    # Si ya viene pegado (CamelCase) se respeta; si trae espacios, se capitaliza.
    camel = raw if " " not in raw else "".join(w.capitalize() for w in raw.split())
    return f"#{camel}"
