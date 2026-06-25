"""Gate de FOCO editorial del contenido (red anti-deriva temática).

Motivo: el motor de noticias arrastra a veces material web del LUGAR/recinto y
acaba dedicando secciones enteras a algo ajeno al protagonista (caso real: los
«Premios Actitud» con un H2 entero sobre la arquitectura del Guggenheim en vez
del homenaje a Robe). El fact-check canónico (canción↔álbum↔año) no caza esto
porque cada dato suelto es "cierto"; lo que falla es el FOCO.

Este módulo evalúa si un artículo se mantiene en su TEMA y, si se desvía, lo
recorta/reescribe quitando el relleno fuera de foco — preservando voz, headings
válidos, enlaces markdown y versos citados. Filosofía del proyecto: ante la
duda, NO inventar; aquí solo se QUITA lo desviado, nunca se añade nada.

Consumidores:
  - Blog (`scripts.blog.materialize_proposals`): gate pre-publicación.
  - Publicación manual (`app.services.publishing.auto_publish_post`).
  - Reproceso del banco (`scripts.blog.reprocess_proposals`).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MODEL = "gpt-4o"

# Por debajo de este foco (0-100) se considera que el artículo se desvía y se
# usa la versión recortada.
FOCUS_THRESHOLD = 70

_SYS = (
    "Eres el editor jefe de Entre Interiores, un sitio sobre Robe y Extremoduro. "
    "Tu trabajo es velar por el FOCO de cada artículo: debe tratar de su TEMA y de "
    "sus PROTAGONISTAS (quién, qué, cuándo, actuaciones, guiños a Robe/Extremoduro). "
    "Lo que se DESVÍA del tema es relleno: secciones o párrafos sobre el LUGAR/"
    "recinto/sede y su historia o arquitectura, contexto enciclopédico ajeno al "
    "protagonista, o divagaciones genéricas. Devuelves SOLO JSON."
)


@dataclass
class FocusReport:
    ok: bool                      # True si el artículo se mantiene en el tema
    score: int                    # 0-100 (cuánto se centra en el tema)
    drift_headings: list[str]     # headings/secciones que se desvían
    trimmed_body_md: str | None   # cuerpo recortado sin la deriva (o None)


def check_focus(body_md: str, subject: str, focus: str = "") -> FocusReport:
    """Evalúa el foco del artículo sobre `subject`. Si se desvía, devuelve un
    `trimmed_body_md` sin el relleno fuera de tema. Degrada a OK si no hay API
    key o el LLM falla (no bloquea la publicación por un fallo de la red de foco;
    el fact-check sigue actuando aparte)."""
    body = (body_md or "").strip()
    if not body or not subject.strip():
        return FocusReport(ok=True, score=100, drift_headings=[], trimmed_body_md=None)

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return FocusReport(ok=True, score=100, drift_headings=[], trimmed_body_md=None)

    user = (
        f"TEMA del artículo: «{subject}».\n"
        + (f"ENFOQUE esperado: {focus}\n" if focus else "")
        + "\nEvalúa el ARTÍCULO de abajo:\n"
        "1. Puntúa de 0 a 100 cuánto se CENTRA en el tema y sus protagonistas "
        "(100 = todo al grano; 0 = se va por las ramas).\n"
        "2. Lista los encabezados (o el inicio de los párrafos) que se DESVÍAN: "
        "relleno sobre el lugar/recinto/sede, su historia o arquitectura, o "
        "cualquier contenido enciclopédico ajeno al protagonista.\n"
        "3. Si hay desviación, devuelve `trimmed_body_md`: el MISMO artículo pero "
        "SIN las partes desviadas (elimina esas secciones/párrafos enteros o "
        "redúcelos a una mención de pasada). NO añadas información nueva, NO "
        "inventes, conserva la voz, los encabezados válidos, los enlaces markdown "
        "y los versos citados tal cual. Si ya está enfocado, devuelve "
        "`trimmed_body_md` = null.\n\n"
        "Devuelve SOLO JSON: {\"score\": int, \"drift_headings\": [..], "
        "\"trimmed_body_md\": <texto o null>}.\n\n"
        f"ARTÍCULO:\n\"\"\"{body[:9000]}\"\"\""
    )

    try:
        from openai import OpenAI

        resp = OpenAI(api_key=key).chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": _SYS},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=3000,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:  # noqa: BLE001 — no bloquear por fallo del gate
        logger.warning("[focus_check] falló: %s", exc)
        return FocusReport(ok=True, score=100, drift_headings=[], trimmed_body_md=None)

    score = int(data.get("score") or 0)
    drift = [str(h) for h in (data.get("drift_headings") or []) if h]
    trimmed = data.get("trimmed_body_md")
    trimmed = trimmed.strip() if isinstance(trimmed, str) else None
    # Salvaguarda: un recorte que se carga >70% del texto es sospechoso; descártalo.
    if trimmed and len(trimmed) < max(300, int(len(body) * 0.3)):
        logger.warning("[focus_check] recorte demasiado agresivo, se ignora")
        trimmed = None

    ok = score >= FOCUS_THRESHOLD and not trimmed
    return FocusReport(
        ok=ok, score=score, drift_headings=drift,
        trimmed_body_md=trimmed if not ok else None,
    )
