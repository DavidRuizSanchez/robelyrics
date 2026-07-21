"""Cliente de Google Search Console para entreinteriores.com (F2.5).

Auth: token OAuth de usuario auto-refrescante de `davidruizsanchez@gmail.com` (dueño
de la propiedad `sc-domain:entreinteriores.com`). Es el equivalente para Gmail PERSONAL
del "bypass" que Convertix hace con domain-wide delegation (que requiere Workspace y no
vale para una cuenta Gmail). Un solo token da acceso a TODAS las propiedades del usuario,
sin darlo de alta por propiedad.

Implementado con `httpx` puro (refresh manual del token) para NO añadir
google-auth/google-api-python-client a la imagen de la API. Nunca lanza hacia arriba en
las funciones de alto nivel: si el token falta o caduca, degrada con un log claro.

Token: JSON con {token?, refresh_token, token_uri, client_id, client_secret, scopes}.
Ruta configurable con env `GSC_TOKEN_PATH` (default ~/.config/entreinteriores/gsc-token.json;
en prod se monta en /credenciales/gsc-token.json).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://searchconsole.googleapis.com/webmasters/v3"
SITE_URL = os.environ.get("GSC_SITE_URL", "sc-domain:entreinteriores.com")


def _token_path() -> Path:
    return Path(os.environ.get("GSC_TOKEN_PATH", "")
                or (Path.home() / ".config" / "entreinteriores" / "gsc-token.json"))


def _load_token() -> dict | None:
    p = _token_path()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        logger.warning("[gsc] sin token en %s (F2.5 inactivo hasta configurarlo)", p)
        return None


def _access_token() -> str | None:
    """Refresca el access_token a partir del refresh_token (OAuth estándar)."""
    tok = _load_token()
    if not tok or not tok.get("refresh_token"):
        return None
    try:
        r = httpx.post(
            tok.get("token_uri", "https://oauth2.googleapis.com/token"),
            data={
                "grant_type": "refresh_token",
                "refresh_token": tok["refresh_token"],
                "client_id": tok["client_id"],
                "client_secret": tok["client_secret"],
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("access_token")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[gsc] no se pudo refrescar el token: %s", exc)
        return None


def is_configured() -> bool:
    return _load_token() is not None


def list_sites() -> list[dict]:
    at = _access_token()
    if not at:
        return []
    try:
        r = httpx.get(f"{_BASE}/sites", headers={"Authorization": f"Bearer {at}"}, timeout=30)
        r.raise_for_status()
        return r.json().get("siteEntry", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("[gsc] list_sites falló: %s", exc)
        return []


def search_analytics(body: dict, site_url: str | None = None) -> list[dict]:
    """Query cruda a Search Analytics. Devuelve `rows` (o [] si falla)."""
    at = _access_token()
    if not at:
        return []
    site = quote(site_url or SITE_URL, safe="")
    try:
        r = httpx.post(
            f"{_BASE}/sites/{site}/searchAnalytics/query",
            headers={"Authorization": f"Bearer {at}", "Content-Type": "application/json"},
            json=body, timeout=60,
        )
        r.raise_for_status()
        return r.json().get("rows", [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("[gsc] searchAnalytics falló: %s", exc)
        return []


def page_query_rows(start_date: str, end_date: str, *, row_limit: int = 25000) -> list[dict]:
    """Filas [page, query] con clicks/impressions/ctr/position en el periodo."""
    return search_analytics({
        "startDate": start_date, "endDate": end_date,
        "dimensions": ["page", "query"], "rowLimit": row_limit,
    })
