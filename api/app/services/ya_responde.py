"""¿La página ya responde a lo que se busca? Última comprobación antes del correo.

`seo_style.responde` es un diccionario: palabras de pregunta → lo que las responde.
El 23-11-2026 hicieron falta dos tandas para cubrir lo que se escapaba («cantantes»
en plural, «grupo anterior» ↔ «entonces vocalista de», «Eduardo» ↔ «Edu», «qué
significa» ↔ una sección «Qué cuenta…»), y cada hueco del diccionario fue un correo
de rechazo: David aprobaba, la ampliación no encontraba nada nuevo y salía `noop`.
Un diccionario siempre se dejará alguna forma de preguntar.

Aquí un modelo lee la página entera y dice, búsqueda a búsqueda, si ya la responde.
Solo se le cree con PRUEBA: tiene que copiar el fragmento que responde, y ese
fragmento tiene que estar literalmente en la página (`cita_valida`). Sin cita
comprobada, la búsqueda sigue siendo hueco.

Falla hacia lo de siempre: sin clave, con la red caída o con una respuesta rota, la
oportunidad sigue su camino como si esto no existiera. Lo peor que puede pasar es
otro rechazo, que es lo que había.
"""
from __future__ import annotations

import json
import logging
import os
import re

from app.services import seo_style
from app.services.openai_chat import openai_chat_kwargs

logger = logging.getLogger(__name__)

# El juez lee la página ENTERA: cortarla es lo que hacía que el editor jefe diera
# por «no dicho» lo que venía más abajo. Las fichas más largas de prod rondan los
# 20.000 caracteres; por encima de esto no se comprueba (y la oportunidad sigue).
MAX_CARACTERES = 40_000
# Una cita de dos palabras («Marea», «en 1997») casa en cualquier sitio y no prueba
# nada. Tres palabras de contenido como mínimo.
MIN_TOKENS_CITA = 3

_SYS = (
    "Eres el editor de Entre Interiores, un sitio sobre Robe y Extremoduro. Te dan "
    "una página publicada y las búsquedas de Google con las que la gente llega a ella. "
    "Tu trabajo es decir, búsqueda a búsqueda, si la página YA le da a quien busca lo "
    "que busca. Devuelves solo JSON."
)

_INSTRUCCIONES = """\
Una búsqueda está RESPONDIDA si quien la teclea encuentra en la página, dicho de forma
explícita, lo que quiere saber:
- pide un dato (de dónde es, cuándo, quiénes son los miembros, en qué grupo estuvo
  antes, cuántos discos) y la página da ESE dato;
- pide el significado o de qué va, y la página lo explica;
- pide la letra o un verso, y la página trae esa letra;
- nombra a alguien con otra grafía o abreviado (Edu / Eduardo, Robe / Roberto) y la
  página habla de esa persona en lo que se pregunta.

NO está respondida si solo salen las palabras sin el dato, si la página lo insinúa sin
decirlo, o si responde a otra cosa parecida. Ante la duda, NO está respondida.

Para cada búsqueda respondida, `cita` es el fragmento de la página que la responde,
COPIADO LETRA POR LETRA del texto de abajo (una o dos frases, sin cambiar nada). La
cita tiene que CONTENER el dato que se pide: si preguntan quién canta, la cita dice
quién canta; si preguntan de dónde es, dice de dónde. Una frase del mismo tema que no
trae el dato no vale. Si no puedes copiar un fragmento así, no está respondida.

Devuelve SOLO JSON:
{"busquedas": [{"busqueda": "<tal cual>", "responde": true|false, "cita": "<fragmento o vacío>"}]}
"""


def texto_de_pagina(body_md: str | None, letra: str = "") -> str:
    """La página como la lee una persona: los enlaces son su texto, sin marcas."""
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", body_md or "")
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"[*_`#>]+", "", t)
    if letra.strip():
        t = f"{t}\n\nLETRA:\n{letra}"
    return re.sub(r"[ \t]+", " ", t).strip()


def cita_valida(cita: str | None, texto: str) -> bool:
    """La cita está en la página, palabra por palabra, y dice algo."""
    plano = seo_style.flatten(cita)
    if len(seo_style.content_tokens(plano)) < MIN_TOKENS_CITA:
        return False
    return plano in seo_style.flatten(texto)


def trae_lo_que_pide(busqueda: str, cita: str) -> bool:
    """Si la búsqueda pregunta algo que el diccionario reconoce, la cita lo responde.

    En el ensayo del 24-11-2026 el modelo dio «cantante marea» por respondida con «el
    proyecto fue iniciado por Kutxi Romero», y la ficha no dice en ningún sitio quién
    canta. Para las palabras que `seo_style` sabe responder («cantante», «dónde»,
    «miembros»…) se le pide a la cita lo mismo que se le pediría a la página. Lo que el
    diccionario no conoce («cuchi», «inata», «naixement») queda a juicio del modelo:
    para eso está.
    """
    cita_plana = seo_style.flatten(cita)
    for palabra in seo_style.flatten(busqueda).split():
        # Si la palabra está en la cita es parte de lo citado, no una pregunta: «el
        # tiempo pasa despacio cuando no te tengo» es un verso, y su «cuando» no pide
        # una fecha.
        if f" {palabra} " in cita_plana:
            continue
        patron = seo_style._patron_de_respuesta(palabra)
        if patron and not re.search(patron, cita_plana):
            return False
    return True


def _llamar(sujeto: str, texto: str, busquedas: list[str]) -> dict | None:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    from openai import OpenAI

    user = (
        f"{_INSTRUCCIONES}\nPÁGINA: {sujeto}\n\nBÚSQUEDAS:\n"
        + "\n".join(f"- {b}" for b in busquedas)
        + f"\n\nTEXTO DE LA PÁGINA:\n\"\"\"\n{texto}\n\"\"\""
    )
    resp = OpenAI(api_key=key).chat.completions.create(
        messages=[{"role": "system", "content": _SYS}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        **openai_chat_kwargs("chat", temperature=0, max_completion_tokens=2500),
    )
    return json.loads(resp.choices[0].message.content or "{}")


def revisar(sujeto: str, texto: str, queries: list[dict], *, llamar=None) -> dict | None:
    """{búsqueda → cita comprobada} de las que la página ya responde.

    `None` si no se pudo comprobar: quien llama sigue como si esto no existiera.
    Un `{}` es «se comprobó y no responde a ninguna».
    """
    busquedas = [q.get("query") or "" for q in queries if (q.get("query") or "").strip()]
    if not busquedas or not texto.strip() or len(texto) > MAX_CARACTERES:
        return None
    try:
        data = (llamar or _llamar)(sujeto, texto, busquedas)
    except Exception as exc:  # noqa: BLE001 — falla hacia lo de antes, nunca bloquea
        logger.warning("[ya_responde] %s: no se pudo comprobar (%s)", sujeto, exc)
        return None
    if not isinstance(data, dict) or not isinstance(data.get("busquedas"), list):
        return None
    pedidas = {seo_style.flatten(b): b for b in busquedas}
    respondidas: dict[str, str] = {}
    for item in data["busquedas"]:
        if not isinstance(item, dict) or item.get("responde") is not True:
            continue
        original = pedidas.get(seo_style.flatten(str(item.get("busqueda") or "")))
        cita = str(item.get("cita") or "").strip()
        if original is None:
            continue
        if not cita_valida(cita, texto) or not trae_lo_que_pide(original, cita):
            # Dice que responde y no lo puede enseñar: se queda como hueco.
            logger.info("[ya_responde] %s: «%s» sin cita comprobable", sujeto, original)
            continue
        respondidas[original] = cita
    return respondidas
