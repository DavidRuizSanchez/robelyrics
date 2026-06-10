"""Verificación externa (Wikipedia / Google) de conexiones y datos.

Regla del proyecto: una afinidad/conexión o un dato fuera del corpus NO se "da
por bueno" sin confirmarlo en una fuente externa autoritativa. Prioriza
Wikipedia (más fiable) sobre snippets de Google; ante duda o contradicción, NO
confirma (mejor omitir que arriesgar). Cachea en `data/verification_cache.json`
para no repetir llamadas web por el mismo par/claim.

Reutiliza `news_research.web_research` (SERP Google vía DataForSEO, ya existente)
y `news_research._json` (juez LLM gpt-4o-mini, barato).
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from urllib.parse import quote, unquote

import httpx

logger = logging.getLogger(__name__)

# El mount /app/data es read-only en prod → la caché va a un dir escribible.
# /tmp persiste durante toda la vida del contenedor (cubre un batch entero).
_CACHE_PATH = Path("/tmp/verification_cache.json")
_LOCK = threading.Lock()

_JUDGE_SYS = (
    "Eres un verificador de hechos riguroso. Te doy una AFIRMACIÓN y EVIDENCIA "
    "externa (Wikipedia y resultados de Google). Responde SOLO JSON: "
    '{"confirmed": true|false, "evidence": "<frase breve que lo respalda>", '
    '"source": "<url o medio>"}. confirmed=true SOLO si la evidencia respalda '
    "claramente la afirmación. Si la evidencia es ambigua, no la menciona o se "
    "contradice, confirmed=false. No inventes."
)


def _load_cache() -> dict:
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[web_verify] no se pudo guardar cache: %s", exc)


def _key(kind: str, *parts: str) -> str:
    raw = kind + "|" + "|".join((p or "").strip().lower() for p in parts)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def wikipedia_extract(title_or_url: str, lang: str = "es") -> str | None:
    """Extracto (summary) de un artículo de Wikipedia. Acepta título o URL."""
    if not title_or_url:
        return None
    title = title_or_url.strip()
    if title.startswith("http"):
        # .../wiki/Roberto_Iniesta → "Roberto_Iniesta"
        title = unquote(title.rstrip("/").split("/wiki/")[-1].split("/")[-1])
        if "es.wikipedia" in title_or_url:
            lang = "es"
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}"
    try:
        with httpx.Client(timeout=15, follow_redirects=True,
                          headers={"User-Agent": "EntreInteriores/1.0 (research)"}) as c:
            r = c.get(url)
            if r.status_code != 200:
                return None
            data = r.json()
            return (data.get("extract") or "").strip() or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[web_verify] wikipedia '%s' falló: %s", title, exc)
        return None


def _gather_evidence(query: str, wiki_titles: list[str]) -> str:
    from app.services.news_research import web_research
    parts: list[str] = []
    for t in wiki_titles:
        ext = wikipedia_extract(t)
        if ext:
            parts.append(f"[Wikipedia · {t}] {ext[:900]}")
    try:
        for hit in web_research(query, n=5):
            parts.append(f"[Google] {hit.get('title','')}: {hit.get('snippet','')}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[web_verify] web_research falló: %s", exc)
    return "\n".join(parts)


def _judge(claim: str, evidence: str) -> dict:
    from app.services.news_research import _json
    if not evidence.strip():
        return {"confirmed": False, "evidence": "", "source": ""}
    out = _json(
        _JUDGE_SYS,
        f"AFIRMACIÓN: {claim}\n\nEVIDENCIA:\n\"\"\"{evidence[:6000]}\"\"\"",
        max_tokens=200,
    )
    return {
        "confirmed": bool(out.get("confirmed")),
        "evidence": (out.get("evidence") or "")[:300],
        "source": (out.get("source") or "")[:300],
    }


def verify_connection(subject_a: str, subject_b: str, hint: str = "") -> dict:
    """¿Están A y B realmente relacionados? Devuelve {confirmed, evidence, source}."""
    k = _key("conn", subject_a, subject_b, hint)
    with _LOCK:
        cache = _load_cache()
        if k in cache:
            return cache[k]
    claim = f"{subject_a} está relacionado/a con {subject_b}" + (f" ({hint})" if hint else "")
    evidence = _gather_evidence(f"{subject_a} {subject_b}", [subject_a, subject_b])
    res = _judge(claim, evidence)
    # Solo si se confirma, se adjunta el TEXTO de evidencia real (Wikipedia/prensa)
    # para que el contenido se ancle en él (grounded), no en memoria paramétrica.
    res["evidence_text"] = evidence[:1800] if res.get("confirmed") else ""
    with _LOCK:
        cache = _load_cache()
        cache[k] = res
        _save_cache(cache)
    return res


def web_context(query: str, wiki_titles: list[str] | None = None, max_chars: int = 1500) -> str:
    """Reúne contexto externo (Wikipedia + Google) para una query y lo devuelve
    como texto (sin juez). Para ENRIQUECER el dossier con datos/nombres que no
    están en el corpus (p.ej. proyectos actuales). Se etiqueta como 'verifica
    antes de afirmar'; el verificador factual de cada sección filtra lo no
    respaldado. Cacheado."""
    k = _key("ctx", query)
    with _LOCK:
        cache = _load_cache()
        if k in cache:
            return cache[k]
    text = _gather_evidence(query, wiki_titles or [])[:max_chars]
    with _LOCK:
        cache = _load_cache()
        cache[k] = text
        _save_cache(cache)
    return text


def verify_fact(claim: str, wiki_title: str = "") -> dict:
    """¿Es cierto este dato? Devuelve {confirmed, evidence, source}."""
    k = _key("fact", claim)
    with _LOCK:
        cache = _load_cache()
        if k in cache:
            return cache[k]
    titles = [wiki_title] if wiki_title else []
    evidence = _gather_evidence(claim, titles)
    res = _judge(claim, evidence)
    with _LOCK:
        cache = _load_cache()
        cache[k] = res
        _save_cache(cache)
    return res
