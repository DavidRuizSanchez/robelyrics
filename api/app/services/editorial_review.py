"""Gate de RIGOR editorial — el "editor jefe" que decide si una pieza merece
publicarse.

Principio UNIVERSAL (todos los tipos de contenido): un texto solo se publica si
demuestra conocimiento CONCRETO y de PRIMERA MANO, con datos específicos y valor
diferencial. Lo genérico —afirmaciones que valdrían para cualquier banda, disco o
evento— NO se publica. Nada de relleno, redundancia ni frases vacías.

Veredicto:
  - "pass":   listo para publicar.
  - "revise": salvable; se devuelve `tightened_body_md` (mismo texto, sin paja ni
              repeticiones). El llamador publica esa versión tensa.
  - "reject": no llega al listón y NO se puede salvar tensando (lo que falta son
              HECHOS, y no se inventan) → no se publica.

Anti-invención (regla dura del proyecto): el critic SOLO condensa/quita; jamás
añade un dato, una cita o un setlist que no esté ya en el cuerpo.

Consumidores: publicación de posts del blog (`auto_publish_post`,
`materialize_proposals`), generación de páginas SEO, reproceso del banco y
auditoría de lo ya publicado.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger(__name__)

MODEL = "gpt-4o"

# Mínimo de palabras de prosa real para que un post sea publicable. NO se rellena
# para alcanzarlo: si no llega con sustancia, se rechaza (o el admin lo fuerza).
MIN_WORDS = 250

Verdict = Literal["pass", "revise", "reject"]


def _word_count(body_md: str) -> int:
    """Cuenta palabras de PROSA real: quita bloques de código, URLs sueltas
    (vídeos embebidos), sintaxis markdown y encabezados de adorno."""
    import re

    t = body_md or ""
    t = re.sub(r"```.*?```", " ", t, flags=re.DOTALL)       # bloques de código
    t = re.sub(r"^\s*https?://\S+\s*$", " ", t, flags=re.MULTILINE)  # URL sola (embed)
    t = re.sub(r"!?\[([^\]]*)\]\([^)]+\)", r"\1", t)         # links/imágenes → texto
    t = re.sub(r"[#>*_`~|-]", " ", t)                        # adornos markdown
    return len([w for w in t.split() if any(c.isalnum() for c in w)])

# Fórmulas vacías típicas (ejemplos para el critic; no es exhaustivo).
_FILLER_EXAMPLES = (
    "rindió homenaje, conectó con el público, dejó (una) huella (imborrable), "
    "una noche inolvidable, la esencia del rock, su legado perdura, marcó un antes "
    "y un después, hizo vibrar al público, no dejó indiferente, puso el broche de oro"
)

# Qué cuenta como "específico" según el tipo de contenido. Calibra el listón sin
# cambiar el principio (concreción + primera mano + valor diferencial).
_RUBRIC: dict[str, str] = {
    "news": (
        "Noticia/actualidad. Si es la CRÓNICA de un evento ya ocurrido, exige al "
        "menos varios de estos detalles REALES: canciones/temas concretos que "
        "sonaron, palabras o dedicatorias sobre Robe/Extremoduro, otros artistas o "
        "invitados presentes (con nombre), una anécdota o momento concreto. Si es el "
        "ANUNCIO de un evento futuro, exige quién/cuándo/dónde/lineup y por qué le "
        "importa a un fan (no se le pide setlist). Genérico ('ofrecieron "
        "actuaciones', 'rindió homenaje') sin detalles → reject."
    ),
    "spotlight": (
        "Análisis de canción. Exige versos citados textualmente, significado "
        "concreto de la letra, música/contexto del disco. Sin versos ni lectura "
        "propia → reject."
    ),
    "evergreen": (
        "Tema de fondo. Exige ejemplos concretos: canciones/versos citados, hechos, "
        "nombres. Reflexión genérica sin anclas → reject."
    ),
    "anniversary": (
        "Efeméride de Robe. Exige hechos biográficos concretos y datados, no "
        "loas genéricas."
    ),
    "album-anniversary": (
        "Aniversario de disco. Exige canciones clave, contexto de grabación, sello, "
        "sonido, lugar en la trayectoria. Sin concreción → reject."
    ),
    "person": "Persona: discografía y proyectos con NOMBRE, hechos datados, relación real con Robe.",
    "band": "Banda: historia, miembros, discos célebres con nombre, vínculo real con Robe/Extremoduro.",
    "album": "Disco: canciones clave, grabación, sonido, contexto. Sin concreción → reject.",
    "song": "Canción: versos citados, significado, música, lugar en el disco.",
    "theme": "Tema/concepto: versos citados que lo encarnan + cómo lo trabaja Robe.",
    "place": "Lugar: relación REAL y concreta con Robe/Extremoduro (canciones, hechos), no contexto turístico.",
    "concept": "Concepto: ejemplos concretos en la obra, versos, hechos.",
}


@dataclass
class EditorialVerdict:
    verdict: Verdict
    score: int                       # 0-100 (cuánto merece leerse un fan)
    reasons: list[str] = field(default_factory=list)
    tightened_body_md: str | None = None


def _rubric_for(kind: str) -> str:
    return _RUBRIC.get(kind, "Contenido general: exige hechos concretos, nombres y datos; nada genérico.")


def review(
    body_md: str,
    *,
    kind: str,
    subject: str,
    focus: str = "",
    material: str | None = None,
    event_when: str | None = None,  # 'past' | 'future' | None (pista para news)
) -> EditorialVerdict:
    """Juzga el rigor de una pieza. Degrada a `pass` si no hay API key o el LLM
    falla (no bloquea la publicación por un fallo de infraestructura; el resto de
    gates siguen actuando)."""
    body = (body_md or "").strip()
    if not body:
        return EditorialVerdict("reject", 0, ["cuerpo vacío"], None)

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return EditorialVerdict("pass", 100, ["sin API key, gate omitido"], None)

    when_line = ""
    if event_when == "past":
        when_line = "Es la CRÓNICA de un evento que YA ocurrió: aplica la vara de crónica (setlist, citas, asistentes, anécdotas).\n"
    elif event_when == "future":
        when_line = (
            "Es el ANUNCIO de un evento FUTURO: vara MÁS LENIENTE. Si indica de forma "
            "CONCRETA quién toca + cuándo + dónde, es ÚTIL para un fan que quiera ir → "
            "'pass' (o 'revise' si hay paja). NO exijas setlist ni 'por qué es "
            "relevante'. Solo 'reject' si es vago incluso en quién/cuándo/dónde.\n"
        )

    material_block = ""
    if material:
        material_block = (
            "\nMATERIAL DISPONIBLE (para juzgar si lo genérico es por falta de "
            "material; NO lo uses para añadir nada al texto):\n"
            f"\"\"\"{material[:4000]}\"\"\"\n"
        )

    # Linter léxico determinista (Eje E): pista concreta para el criterio 7, para
    # que el editor no dependa solo de su "olfato" con la repetición.
    _lexical_note = ""
    try:
        from app.services.text_sanitizer import lexical_repetition_report

        _rep = lexical_repetition_report(body, allowed={(subject or "").lower()})
        if _rep.has_problems:
            _lexical_note = (
                "AVISO del linter (detección determinista, tenlo MUY en cuenta en los "
                f"criterios 6 y 7): {_rep.summary()}.\n"
            )
    except Exception:  # noqa: BLE001 — nunca romper el gate por el linter
        _lexical_note = ""

    sys = (
        "Eres el editor jefe de Entre Interiores, un sitio sobre Robe y Extremoduro, "
        "y eres DURÍSIMO con la calidad. Solo aprueblas piezas que un fan de "
        "Extremoduro querría leer de verdad: concretas, de primera mano, con datos "
        "específicos y una mirada diferencial. RECHAZAS sin piedad el relleno, la "
        "redundancia y lo genérico. Devuelves SOLO JSON.\n"
        "CONTEXTO FACTUAL (no lo penalices como error): Roberto Iniesta 'Robe', líder "
        "de Extremoduro, FALLECIÓ en diciembre de 2025; un texto que hable de él en "
        "pasado o mencione su muerte es CORRECTO, no un fallo. Extremoduro se disolvió "
        "en 2018 y Robe siguió en solitario. No bajes la nota por estos hechos."
    )
    user = (
        f"TIPO: {kind}. PROTAGONISTA: «{subject}».\n"
        f"{when_line}"
        f"QUÉ EXIGE ESTE TIPO: {_rubric_for(kind)}\n"
        + (f"ENFOQUE esperado: {focus}\n" if focus else "")
        + "\nEvalúa el ARTÍCULO con estos criterios DUROS:\n"
        "1. ESPECIFICIDAD Y PRIMERA MANO: ¿aporta detalles concretos y trazables "
        "(nombres propios, canciones/versos, fechas, citas textuales, cifras, "
        "anécdotas) o son afirmaciones genéricas que valdrían para cualquier "
        "banda/disco/evento? Lo genérico es el peor pecado.\n"
        "2. REDUNDANCIA: ¿repite el mismo hecho o idea en varias secciones con otras "
        "palabras? (p.ej. decir N veces 'banda tributo', 'rindió homenaje').\n"
        f"3. RELLENO: ¿usa fórmulas vacías ({_FILLER_EXAMPLES})?\n"
        "4. VALOR DIFERENCIAL: ¿aporta algo que un fan no encuentre ya en una ficha "
        "o un cartel genérico?\n"
        "5. DESARROLLO: un post de apenas unas frases, sin desarrollo, NO es "
        "publicable aunque sea correcto (mínimo ~250 palabras de sustancia real). "
        "Si no hay material para desarrollarlo, es 'reject' (jamás se rellena).\n"
        "6. SOBRE-INTERPRETACIÓN / PSEUDO-ERUDICIÓN: NO vale llamar 'metáfora' o "
        "'símbolo' a lo que es una afirmación DIRECTA (p.ej. una crítica social "
        "explícita no es 'una metáfora poderosa'), ni adornar con lirismo hueco no "
        "trazable a las fuentes/versos. Una lectura floja disfrazada de honda es un "
        "defecto: exige que la interpretación nazca de un detalle real (un verso, "
        "una decisión musical, algo que dijo Robe), no de tópico literario.\n"
        "7. VARIEDAD LÉXICA: penaliza la repetición machacona de una misma palabra "
        "distintiva o muletilla.\n"
        + _lexical_note +
        "\nPuntúa de 0 a 100 (100 = imprescindible y concreto; 0 = paja genérica).\n"
        "Decide el VEREDICTO:\n"
        " - 'pass' si ya está concreto y sin relleno.\n"
        " - 'revise' si tiene sustancia real pero hay redundancia/relleno que QUITAR: "
        "entonces devuelve `tightened_body_md` con el MISMO artículo condensado "
        "(elimina repeticiones y frases vacías, conserva TODOS los datos concretos, "
        "los encabezados útiles, los enlaces markdown y los versos citados). PUEDE "
        "quedar bastante más corto: mejor breve y denso.\n"
        " - 'reject' si es GENÉRICO o le faltan los específicos que exige su tipo: no "
        "se puede salvar tensando porque lo que falta son HECHOS, y NO se inventan. "
        "También 'reject' si tras quitar la paja no quedaría nada que merezca leerse.\n"
        "REGLA DURA: en `tightened_body_md` NUNCA añadas un dato, cita o canción que "
        "no esté ya en el artículo. Solo se quita y se condensa.\n\n"
        "Devuelve SOLO JSON: {\"score\": int, \"verdict\": \"pass|revise|reject\", "
        "\"reasons\": [\"...\"], \"tightened_body_md\": <texto o null>}.\n"
        f"{material_block}\n"
        f"ARTÍCULO:\n\"\"\"{body[:9000]}\"\"\""
    )

    try:
        from openai import OpenAI

        resp = OpenAI(api_key=key).chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=3500,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:  # noqa: BLE001 — no bloquear por fallo del gate
        logger.warning("[editorial_review] falló: %s", exc)
        return EditorialVerdict("pass", 100, ["gate falló, omitido"], None)

    score = int(data.get("score") or 0)
    verdict = data.get("verdict")
    reasons = [str(r) for r in (data.get("reasons") or []) if r][:6]
    tightened = data.get("tightened_body_md")
    tightened = tightened.strip() if isinstance(tightened, str) else None

    if verdict not in ("pass", "revise", "reject"):
        # Sin veredicto fiable: decide por score.
        verdict = "pass" if score >= 70 else "reject"

    if verdict == "revise":
        # Necesita una versión tensa válida; si no la hay (o es un recorte
        # absurdo), no es salvable → reject.
        if not tightened or len(tightened) < max(200, int(len(body) * 0.2)):
            verdict, tightened = "reject", None
        else:
            from app.services.text_sanitizer import strip_ai_tells
            tightened = strip_ai_tells(tightened) or tightened

    # SUELO DE LONGITUD: el texto que se publicaría (tensado si revise, original
    # si pass) debe tener ≥ MIN_WORDS palabras de prosa real. Si no llega, no es
    # publicable (sin rellenar): reject. No aplica a 'reject' (ya fuera).
    if verdict in ("pass", "revise"):
        final_body = tightened if verdict == "revise" else body
        words = _word_count(final_body)
        if words < MIN_WORDS:
            verdict, tightened = "reject", None
            reasons = (reasons or []) + [
                f"demasiado corto ({words} palabras < {MIN_WORDS}); "
                "sin material para ampliarlo con sustancia"
            ]

    return EditorialVerdict(
        verdict=verdict,  # type: ignore[arg-type]
        score=score,
        reasons=reasons,
        tightened_body_md=tightened if verdict == "revise" else None,
    )
