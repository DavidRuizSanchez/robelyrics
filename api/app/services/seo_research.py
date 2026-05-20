"""Wrapper de la API de DataForSEO para keyword research.

Se usa desde `scripts/blog/generate_proposals.py` para descubrir, a partir
de unas semillas del universo Robe/Extremoduro, qué busca de verdad la
gente — y proponer artículos sobre esa demanda real, no sobre temas
internos sin volumen.

Credenciales: env `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD`.
Mercado por defecto: España (location_code 2724), español.
"""
from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://api.dataforseo.com/v3"
LOCATION_SPAIN = 2724
LANG_ES = "es"


@dataclass(frozen=True)
class KeywordData:
    keyword: str
    volume: int
    cpc: float | None
    competition: float | None

    def as_dict(self) -> dict:
        return {
            "keyword": self.keyword,
            "volume": self.volume,
            "cpc": self.cpc,
            "competition": self.competition,
        }


def _auth_header() -> dict[str, str]:
    login = os.environ.get("DATAFORSEO_LOGIN")
    password = os.environ.get("DATAFORSEO_PASSWORD")
    if not login or not password:
        raise RuntimeError("DATAFORSEO_LOGIN/PASSWORD no configurados")
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def _post(endpoint: str, payload: list[dict], timeout: float = 60.0) -> dict | None:
    """POST a DataForSEO. Devuelve el primer `result` o None si falla."""
    try:
        with httpx.Client(timeout=timeout, headers=_auth_header()) as client:
            resp = client.post(f"{API_BASE}/{endpoint}", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("DataForSEO %s falló: %s", endpoint, exc)
        return None
    task = (data.get("tasks") or [{}])[0]
    if task.get("status_code") != 20000:
        logger.warning(
            "DataForSEO %s task error: %s", endpoint, task.get("status_message")
        )
        return None
    return task


def keyword_suggestions(
    seed: str, *, limit: int = 60, min_volume: int = 30
) -> list[KeywordData]:
    """Sugerencias de keywords para una semilla, ordenadas por volumen.
    Filtra las de volumen < min_volume."""
    task = _post(
        "dataforseo_labs/google/keyword_suggestions/live",
        [{
            "keyword": seed,
            "location_code": LOCATION_SPAIN,
            "language_code": LANG_ES,
            "limit": limit,
            "order_by": ["keyword_info.search_volume,desc"],
        }],
    )
    if not task:
        return []
    result = (task.get("result") or [{}])[0]
    out: list[KeywordData] = []
    for item in result.get("items") or []:
        ki = item.get("keyword_info") or {}
        vol = ki.get("search_volume") or 0
        if vol < min_volume:
            continue
        out.append(KeywordData(
            keyword=item.get("keyword", ""),
            volume=vol,
            cpc=ki.get("cpc"),
            competition=ki.get("competition"),
        ))
    return out


def search_volume(keywords: list[str]) -> dict[str, KeywordData]:
    """Volumen de búsqueda de una lista concreta de keywords.
    Devuelve {keyword_lower: KeywordData}."""
    if not keywords:
        return {}
    task = _post(
        "keywords_data/google/search_volume/live",
        [{
            "keywords": keywords[:700],
            "location_code": LOCATION_SPAIN,
            "language_code": LANG_ES,
        }],
    )
    if not task:
        return {}
    out: dict[str, KeywordData] = {}
    for row in task.get("result") or []:
        kw = row.get("keyword", "")
        out[kw.lower()] = KeywordData(
            keyword=kw,
            volume=row.get("search_volume") or 0,
            cpc=row.get("cpc"),
            competition=row.get("competition"),
        )
    return out
