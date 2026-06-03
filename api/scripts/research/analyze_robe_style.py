"""Analiza CÓMO habla Robe (registro, no qué piensa) a partir de las
transcripciones de entrevistas reales (InterpretationSource kind=robe_interview)
y destila un MANUAL DE ESTILO DE HABLA que se inyecta en el prompt del
consultorio "Pregúntale al viento".

Objetivo: que las respuestas suenen a su lengua de calle, directa, no a prosa
pulida. Todo sale de transcripciones reales; el manual describe patrones
observados + ejemplos VERBATIM (no inventa).

Salida: imprime el manual por stdout. Guardarlo en data/robe_speech_style.md
(en local /app/data es read-only: escribir a /tmp y docker cp, o redirigir).

Ejecución:
    docker compose exec api python -m scripts.research.analyze_robe_style
"""
from __future__ import annotations

from openai import OpenAI

from app.config import get_settings
from app.db.models import InterpretationSource
from scripts.research.common import get_session, log

MODEL = "gpt-4o"
MAX_CHARS_PER_SOURCE = 18000  # acota tokens por entrevista

_SYS = """\
Eres analista de estilo lingüístico. Te doy transcripciones REALES de Robe
Iniesta (Extremoduro) hablando en entrevistas. Analiza SOLO CÓMO HABLA, no qué
piensa: su registro y su forma, para que otro pueda imitar su MANERA de decir
las cosas sin copiar contenido.

Fíjate en: nivel de lengua (culto vs de calle), muletillas y conectores que
repite, longitud y ritmo de las frases, uso de tacos y expresiones malsonantes,
humor e ironía, extremeñismos/castellano del sur, cómo arranca una respuesta,
cómo la cierra, cómo esquiva o quita hierro, cómo trata al que pregunta.

Devuelve EN MARKDOWN, conciso y accionable, exactamente estas secciones:

## Cómo suena (manual de voz)
8-12 viñetas imperativas y concretas ("habla en frases cortas y secas", "usa
'¿sabes?' y 'o sea' para enganchar", "remata con una boutade"...). Nada genérico.

## Muletillas y expresiones suyas (verbatim)
Lista de 12-18 palabras/coletillas/expresiones REALES que usa, tal cual aparecen
(p.ej. tacos, "joder", "tío", "a mí me la suda", giros). Solo las que veas en el texto.

## Cómo NO debe sonar
4-6 viñetas de lo que romperia la voz (cursi, académico, corporativo, "potencial
increíble", "rincón en el mundo", marketing).

## Ejemplos verbatim (su forma de hablar)
6-8 frases CORTAS copiadas literalmente de las transcripciones que ejemplifiquen
su manera de hablar. Entre comillas, fieles al original.

Reglas: todo se basa SOLO en las transcripciones dadas. No inventes muletillas ni
ejemplos. Prohibido el em-dash (— –): usa comas o puntos."""


def main() -> None:
    settings = get_settings()
    if not settings.openai_api_key:
        log("OPENAI_API_KEY no configurada", "err")
        return
    with get_session() as db:
        sources = (
            db.query(InterpretationSource)
            .filter(InterpretationSource.kind == "robe_interview")
            .all()
        )
        blocks = []
        for s in sources:
            txt = (s.content_clean or "")[:MAX_CHARS_PER_SOURCE]
            if len(txt) > 200:
                blocks.append(f"### {s.title}\n{txt}")
    log(f"{len(blocks)} transcripciones de Robe para el análisis")
    if not blocks:
        log("sin transcripciones robe_interview; corre la transcripción primero", "err")
        return

    corpus = "\n\n".join(blocks)
    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _SYS},
            {"role": "user", "content": f"TRANSCRIPCIONES:\n\n{corpus}"},
        ],
        temperature=0.3,
    )
    print(resp.choices[0].message.content or "")


if __name__ == "__main__":
    main()
