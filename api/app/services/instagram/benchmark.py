"""Lectura de cuentas de Instagram ajenas vía `business_discovery` (oficial).

Sirve para estudiar QUÉ y CÓMO publican las cuentas de referencia, con datos
reales de la Graph API — nunca scrapeando ni disfrazando el User-Agent.

Límites que impone Meta y que hay que asumir (no se disimulan, se reportan):

  - Solo alcanza cuentas **Business/Creator**. Una cuenta personal devuelve
    error y aquí se marca `ok=False` con el mensaje literal de la API.
  - No existe endpoint para listar a quién sigue una cuenta: la lista de
    usernames se aporta a mano (o desde el export oficial de "Descargar tu
    información").
  - Las cuentas con restricción de edad no devuelven datos.

Requiere token con `instagram_basic`, `instagram_manage_insights` y
`pages_read_engagement` (los mismos que ya usa la publicación).
"""
from __future__ import annotations

import logging

import httpx

from app.services.instagram import config
from app.services.instagram.graph_api import GRAPH

logger = logging.getLogger(__name__)

# Campos del perfil ajeno. Son los públicos que documenta Meta.
PROFILE_FIELDS = (
    "username,name,biography,website,followers_count,follows_count,media_count"
)

# Campos de cada publicación, del set más rico al mínimo garantizado. Si la API
# rechaza uno (varía por versión y por cuenta), se reintenta con el siguiente
# nivel en vez de dar el análisis por perdido.
MEDIA_FIELD_SETS = [
    "id,caption,media_type,media_product_type,timestamp,permalink,"
    "like_count,comments_count,view_count",
    "id,caption,media_type,media_product_type,timestamp,permalink,"
    "like_count,comments_count",
    "id,caption,media_type,timestamp,permalink,like_count,comments_count",
    "id,like_count,comments_count",
]


def _clean_username(raw: str) -> str:
    """'@Cuenta / ' o una URL de perfil → 'cuenta'."""
    u = (raw or "").strip().strip("/")
    if "instagram.com" in u:
        u = u.split("instagram.com", 1)[1].strip("/").split("/")[0].split("?")[0]
    return u.lstrip("@").strip().lower()


def _query(username: str, media_fields: str, media_limit: int, after: str | None) -> str:
    """Construye la expansión de campos de business_discovery."""
    paging = f".after({after})" if after else ""
    return (
        f"business_discovery.username({username})"
        f"{{{PROFILE_FIELDS},"
        f"media.limit({media_limit}){paging}{{{media_fields}}}}}"
    )


def _call(fields: str) -> dict:
    with httpx.Client(timeout=40.0) as client:
        resp = client.get(
            f"{GRAPH}/{config.INSTAGRAM_ACCOUNT_ID}",
            params={"fields": fields, "access_token": config.INSTAGRAM_ACCESS_TOKEN},
        )
    try:
        return resp.json()
    except Exception:  # noqa: BLE001 — respuesta no-JSON (proxy, HTML de error)
        return {"error": {"message": f"Respuesta no-JSON (HTTP {resp.status_code})"}}


def discover(username: str, media_limit: int = 50, max_posts: int = 100) -> dict:
    """Perfil + últimas publicaciones de una cuenta ajena.

    Devuelve siempre un dict con la misma forma, tanto si sale bien como si no:
    el que falla se queda con `ok=False` y el `error` literal de la API, para
    que el análisis pueda decir CUÁNTAS cuentas no se pudieron leer y por qué.
    """
    user = _clean_username(username)
    out: dict = {
        "username": user,
        "ok": False,
        "error": None,
        "field_set": None,
        "profile": None,
        "media": [],
        "truncated": False,
    }
    if not user:
        out["error"] = "Username vacío"
        return out
    if not (config.INSTAGRAM_ACCOUNT_ID and config.INSTAGRAM_ACCESS_TOKEN):
        out["error"] = "Faltan INSTAGRAM_ACCOUNT_ID / INSTAGRAM_ACCESS_TOKEN"
        return out

    # 1) Primera página, degradando el set de campos si la API rechaza alguno.
    data: dict = {}
    used_fields: str | None = None
    for fields in MEDIA_FIELD_SETS:
        data = _call(_query(user, fields, media_limit, None))
        if "error" not in data:
            used_fields = fields
            break
        msg = data["error"].get("message", "")
        # Solo merece reintentar si el fallo es por un campo no soportado; si la
        # cuenta no existe o no es Business, bajar de campos no arregla nada.
        if "nonexisting field" not in msg.lower() and "unsupported get request" not in msg.lower():
            break

    if "error" in data:
        err = data["error"]
        out["error"] = f'{err.get("message", "error desconocido")} (code={err.get("code")})'
        return out

    bd = (data.get("business_discovery") or {})
    if not bd:
        out["error"] = "La API respondió sin business_discovery (cuenta no alcanzable)"
        return out

    media_block = bd.pop("media", {}) or {}
    out["ok"] = True
    out["field_set"] = used_fields
    out["profile"] = bd
    out["media"] = list(media_block.get("data") or [])

    # 2) Paginación hasta `max_posts`. El tope se REPORTA, no se silencia.
    after = ((media_block.get("paging") or {}).get("cursors") or {}).get("after")
    while after and len(out["media"]) < max_posts and used_fields:
        page = _call(_query(user, used_fields, media_limit, after))
        if "error" in page:
            logger.warning("[benchmark] %s: paginación cortada: %s", user, page["error"])
            break
        block = ((page.get("business_discovery") or {}).get("media") or {})
        rows = list(block.get("data") or [])
        if not rows:
            break
        out["media"].extend(rows)
        after = ((block.get("paging") or {}).get("cursors") or {}).get("after")

    if len(out["media"]) > max_posts:
        out["media"] = out["media"][:max_posts]
    out["truncated"] = bool(after) and len(out["media"]) >= max_posts
    return out
