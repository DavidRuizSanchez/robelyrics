"""Fetchers de letras multi-fuente para el consenso de verificación.

La verdad de la letra ya no es solo Genius. Estos fetchers traen la letra de una
canción de fuentes abiertas e independientes para poder VOTAR: si dos o más
coinciden en algo distinto de lo que tenemos, el Motor de Consenso lo corrige.

Fuentes (sin scraping evasivo, User-Agent honesto, reintentos y degradación
elegante si una está caída):
  - LRCLIB  (T2): API JSON abierta de letras.
  - letras.com (T2): scrape best-effort del HTML público.
  - (Vagalume queda como hueco: requiere API key; se añade cuando se configure.)

Cada fetcher devuelve texto plano (líneas separadas por \n) o None. Nunca lanza:
una fuente caída no puede tumbar el consenso.
"""
from __future__ import annotations

import logging
import re
import time
import unicodedata

import httpx

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "RobeLyrics/1.0 (https://entreinteriores.com; davidruizsanchez@gmail.com)"}
_LRC = "https://lrclib.net/api"


def _norm(s: str) -> str:
    """Normaliza para comparar títulos/artistas: sin acentos, sin puntuación."""
    s = "".join(
        ch for ch in unicodedata.normalize("NFD", (s or "").lower())
        if unicodedata.category(ch) != "Mn"
    )
    s = re.sub(r"[\(\[].*?[\)\]]", "", s)     # quita "(en directo)", "[remix]"
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _title_matches(candidate: str, want: str) -> bool:
    """Match tolerante: LRCLIB a veces da títulos sucios ('14.Extremoduro_A fuego').
    Aceptamos si el título buscado aparece como palabra dentro del candidato."""
    c, w = _norm(candidate), _norm(want)
    if not w:
        return False
    if c == w:
        return True
    # "a fuego" dentro de "14 extremoduro a fuego"
    return bool(re.search(rf"\b{re.escape(w)}\b", c))


def _get_json(client: httpx.Client, url: str, params: dict, *, retries: int = 3):
    """GET con reintentos ante 5xx/errores de red (LRCLIB devuelve 502 a ratos)."""
    for attempt in range(retries):
        try:
            r = client.get(url, params=params)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
                return r.json()
            if r.status_code < 500:
                return None  # 4xx: no reintentar
        except Exception as exc:  # noqa: BLE001
            logger.debug("[lyric_fetchers] %s intento %d: %s", url, attempt + 1, exc)
        time.sleep(1.5 * (attempt + 1))
    return None


def fetch_lrclib(title: str, artist: str = "Extremoduro") -> str | None:
    """Letra plana de LRCLIB (la más larga = estudio completa). None si no hay."""
    try:
        with httpx.Client(timeout=25, headers=_UA, follow_redirects=True) as client:
            data = _get_json(client, f"{_LRC}/search", {"q": f"{artist} {title}"})
    except Exception as exc:  # noqa: BLE001
        logger.warning("[lyric_fetchers] lrclib '%s' falló: %s", title, exc)
        return None
    if not isinstance(data, list):
        return None
    cands: list[str] = []
    for x in data:
        if _norm(artist) not in _norm(x.get("artistName") or ""):
            continue
        name = x.get("trackName") or ""
        if not _title_matches(name, title):
            continue
        if re.search(r"live|directo|fragmento|en vivo", name, re.IGNORECASE):
            continue
        ly = (x.get("plainLyrics") or "").strip()
        if ly:
            cands.append(ly)
    return max(cands, key=len) if cands else None


# --- letras.com (scrape best-effort) --------------------------------------- #
_RE_LETRAS_BLOCK = re.compile(r'<div[^>]+class="[^"]*lyric-original[^"]*"[^>]*>(.*?)</div>', re.DOTALL)


def fetch_letras_com(title: str, artist: str = "Extremoduro") -> str | None:
    """Scrape de la letra en letras.com. Best-effort: si cambia el HTML o no
    resuelve el slug, devuelve None sin romper."""
    from urllib.parse import quote

    def _slug(s: str) -> str:
        s = "".join(
            ch for ch in unicodedata.normalize("NFD", s.lower())
            if unicodedata.category(ch) != "Mn"
        )
        return re.sub(r"[^a-z0-9]+", "-", s).strip("-")

    url = f"https://www.letras.com/{_slug(artist)}/{_slug(title)}/"
    try:
        with httpx.Client(timeout=20, headers=_UA, follow_redirects=True) as client:
            r = client.get(url)
            if r.status_code != 200:
                # fallback: buscador interno
                sr = client.get("https://www.letras.com/api/search/", params={"q": f"{artist} {title}"})
                return None if sr.status_code != 200 else _extract_letras(sr.text)
            return _extract_letras(r.text)
    except Exception as exc:  # noqa: BLE001
        logger.debug("[lyric_fetchers] letras.com '%s' falló: %s", title, exc)
        return None


def _extract_letras(html: str) -> str | None:
    m = _RE_LETRAS_BLOCK.search(html)
    if not m:
        return None
    block = m.group(1)
    block = re.sub(r"<br\s*/?>", "\n", block, flags=re.IGNORECASE)
    block = re.sub(r"</p>", "\n", block, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", block)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text or None


# Registro de fetchers con su source_kind (tier lo pone consensus.py).
FETCHERS: list[tuple[str, callable]] = [
    ("lrclib", fetch_lrclib),
    ("letras_com", fetch_letras_com),
]


def fetch_all(title: str, artist: str = "Extremoduro") -> dict[str, str]:
    """Trae la letra de todas las fuentes disponibles. Devuelve {source_kind: texto}
    solo con las que respondieron."""
    out: dict[str, str] = {}
    for kind, fn in FETCHERS:
        try:
            txt = fn(title, artist)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[lyric_fetchers] %s reventó: %s", kind, exc)
            txt = None
        if txt:
            out[kind] = txt
    return out
