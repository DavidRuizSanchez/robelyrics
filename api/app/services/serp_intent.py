"""Validación de INTENCIÓN DE BÚSQUEDA por SERP para las propuestas SEO del blog.

Antes de proponer un artículo por una keyword, miramos su SERP REAL (DataForSEO,
mercado España) y decidimos si:

  - la intención es INFORMACIONAL (un artículo editorial puede satisfacerla), y
  - nuestro sitio (contenido sobre Robe/Extremoduro) puede razonablemente cubrirla
    y competir — descartando KW navegacionales (marca/oficial/redes), transaccionales
    (tienda/entradas/streaming) o dominadas por sitios de letras de terceros.

Así evitamos gastar una pieza en una keyword que no vamos a posicionar o cuya
intención no encaja con un artículo. El veredicto se CACHEA por keyword durante la
ejecución para no repetir llamadas (SERP + LLM ligero).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Dominios cuya presencia dominante en el top del SERP delata una intención que
# un artículo editorial NO satisface (o no va a superar).
_LYRICS_DOMAINS = (
    "genius.com", "letras.com", "letras.mus.br", "musica.com", "tusletras",
    "azlyrics.com", "lyrics", "coveralia.com", "songlyrics",
)
_SHOP_DOMAINS = (
    "amazon.", "fnac.", "elcorteingles", "discogs.com", "ebay.", "wallapop",
    "ticketmaster", "entradas.com", "wegow.com", "elcorteingles", "aliexpress",
)
_STREAMING_DOMAINS = (
    "spotify.com", "music.apple.com", "deezer.com", "tidal.com", "napster",
)
_SOCIAL_DOMAINS = (
    "instagram.com", "facebook.com", "twitter.com", "x.com", "tiktok.com",
)
# YouTube y Wikipedia NO descartan: son SERP mixtas informacionales habituales.


def _domain(url: str) -> str:
    try:
        d = (urlparse(url).netloc or "").lower()
        return d[4:] if d.startswith("www.") else d
    except Exception:  # noqa: BLE001
        return ""


def _hits(url: str, needles: tuple[str, ...]) -> bool:
    d = _domain(url)
    return any(n in d for n in needles)


@dataclass
class Verdict:
    keyword: str
    coverable: bool
    intent: str  # informational|navigational|transactional|lyrics|unknown
    top_titles: list[str] = field(default_factory=list)
    reason: str = ""


_CACHE: dict[str, Verdict] = {}


def _heuristic(keyword: str, serp: list[dict]) -> Verdict | None:
    """Veredicto rápido por dominios del top-5. Devuelve None si es ambiguo (→ LLM)."""
    top = serp[:5]
    titles = [r.get("title", "") for r in top if r.get("title")]
    if not top:
        # Sin SERP (o sin credenciales): no bloqueamos, dejamos pasar como unknown.
        return Verdict(keyword, True, "unknown", titles, "sin datos de SERP")
    urls = [r.get("url", "") for r in top]
    lyrics = sum(1 for u in urls if _hits(u, _LYRICS_DOMAINS))
    shop = sum(1 for u in urls if _hits(u, _SHOP_DOMAINS))
    stream = sum(1 for u in urls if _hits(u, _STREAMING_DOMAINS))
    social = sum(1 for u in urls if _hits(u, _SOCIAL_DOMAINS))
    if lyrics >= 3:
        return Verdict(keyword, False, "lyrics", titles, "SERP dominado por sitios de letras")
    if shop + stream >= 3:
        return Verdict(keyword, False, "transactional", titles,
                       "SERP dominado por tienda/streaming")
    if social >= 3:
        return Verdict(keyword, False, "navigational", titles, "SERP dominado por redes")
    return None  # ambiguo → que decida el LLM (si hay)


_LLM_SYS = """\
Eres analista SEO. Te doy una keyword en español y los títulos del top del SERP de
Google (España). Decide la INTENCIÓN DE BÚSQUEDA dominante y si un ARTÍCULO
EDITORIAL de un sitio de fans sobre Robe Iniesta / Extremoduro podría satisfacerla
y competir por posicionar.

Marca coverable=false si la intención es claramente:
  - navegacional (busca un sitio/perfil/canal oficial concreto),
  - transaccional (comprar entradas, discos, merch, streaming),
  - o es una consulta de LETRA de canción (mejor servida por páginas de letra).
Marca coverable=true si es informacional (biografía, historia, contexto, listas,
significado, análisis, curiosidades, relaciones) que un artículo puede cubrir.

Devuelve JSON: {"intent": "informational|navigational|transactional|lyrics",
"coverable": true|false, "reason": "breve"}."""


def _llm_verdict(client, keyword: str, titles: list[str]) -> Verdict:
    if client is None:
        # Sin LLM: por defecto NO bloqueamos lo ambiguo (el heurístico ya filtró lo claro).
        return Verdict(keyword, True, "unknown", titles, "sin LLM; ambiguo aceptado")
    import json
    user = (
        f"Keyword: {keyword}\n\nTítulos del top del SERP:\n"
        + "\n".join(f"- {t}" for t in titles[:8])
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": _LLM_SYS},
                      {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=200,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[serp_intent] LLM falló '%s': %s", keyword, exc)
        return Verdict(keyword, True, "unknown", titles, "LLM error; aceptado")
    return Verdict(
        keyword,
        bool(data.get("coverable", True)),
        str(data.get("intent") or "unknown"),
        titles,
        str(data.get("reason") or "")[:200],
    )


def classify(keyword: str, *, client=None) -> Verdict:
    """Clasifica la intención de una keyword mirando su SERP real. Cacheado por run.

    Nunca lanza: ante cualquier fallo (sin credenciales DataForSEO, sin LLM, error de
    red) devuelve un veredicto permisivo (coverable=True, intent='unknown') para no
    bloquear la generación por infraestructura."""
    key = re.sub(r"\s+", " ", (keyword or "").strip().lower())
    if not key:
        return Verdict(keyword, False, "unknown", [], "keyword vacía")
    if key in _CACHE:
        return _CACHE[key]
    try:
        from app.services.news_research import web_research
        serp = web_research(keyword, n=6)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[serp_intent] SERP falló '%s': %s", keyword, exc)
        serp = []
    verdict = _heuristic(keyword, serp)
    if verdict is None:
        titles = [r.get("title", "") for r in serp[:5] if r.get("title")]
        verdict = _llm_verdict(client, keyword, titles)
    _CACHE[key] = verdict
    logger.info("[serp_intent] '%s' -> intent=%s coverable=%s (%s)",
                keyword, verdict.intent, verdict.coverable, verdict.reason)
    return verdict
