"""Brief de competencia SERP para SUPERAR a los que ya rankean por una keyword.

IMPORTANTE (veracidad): el SERP se usa SOLO como GUÍA DE COBERTURA — qué ángulos
tratan los que ya rankean, para cubrirlos y superarlos — NUNCA como fuente de
HECHOS. Los hechos siguen viniendo exclusivamente del corpus verificado; el
verificador por sección sigue tumbando cualquier afirmación no respaldada. Por eso
el brief se inyecta como instrucción de qué cubrir, no como "material".
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def build_brief(keyword: str, *, n: int = 5) -> str:
    """Devuelve una instrucción de cobertura basada en los títulos de los top
    resultados de la keyword (DataForSEO SERP). Cadena vacía si no hay datos."""
    kw = (keyword or "").strip()
    if not kw:
        return ""
    try:
        from app.services.news_research import web_research

        hits = web_research(kw, n=n)
    except Exception as exc:  # noqa: BLE001
        logger.warning("serp_brief: SERP falló para «%s»: %s", kw, exc)
        return ""
    titles = [h.get("title", "").strip() for h in (hits or []) if h.get("title")]
    titles = [t for t in titles if t][:n]
    if not titles:
        return ""
    listado = "; ".join(t[:90] for t in titles)
    return (
        "COBERTURA A SUPERAR (lo que ya rankea por esta búsqueda; trata estos "
        "ángulos y algunos más, con MÁS profundidad y detalle, pero usando SOLO "
        f"hechos del material del corpus —nunca copies ni afirmes nada de estos "
        f"títulos—): {listado}"
    )
