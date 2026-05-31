"""Cliente de la Instagram Graph API (publicación de fotos).

Flujo oficial en 2 pasos: crear el container de media → publicar el container.
Docs: https://developers.facebook.com/docs/instagram-platform/content-publishing
"""
from __future__ import annotations

import logging
import time

import httpx

from app.services.instagram import config

logger = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v21.0"


def account_info() -> dict:
    """Devuelve info de la cuenta IG (para verificar el token)."""
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(
            f"{GRAPH}/{config.INSTAGRAM_ACCOUNT_ID}",
            params={
                "fields": "username,name,followers_count,media_count",
                "access_token": config.INSTAGRAM_ACCESS_TOKEN,
            },
        )
        return resp.json()


def token_is_valid() -> tuple[bool, str]:
    """Comprueba que el token tiene permiso para publicar."""
    if not config.INSTAGRAM_ACCESS_TOKEN:
        return False, "Falta INSTAGRAM_ACCESS_TOKEN"
    if not (config.META_APP_ID and config.META_APP_SECRET):
        return False, "Faltan META_APP_ID / META_APP_SECRET"
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(
            f"{GRAPH}/debug_token",
            params={
                "input_token": config.INSTAGRAM_ACCESS_TOKEN,
                "access_token": f"{config.META_APP_ID}|{config.META_APP_SECRET}",
            },
        )
    data = resp.json().get("data", {})
    if not data.get("is_valid"):
        return False, "Token inválido o caducado"
    scopes = set(data.get("scopes", []))
    if "instagram_content_publish" not in scopes:
        return False, (
            f"Falta el permiso instagram_content_publish. "
            f"Scopes: {sorted(scopes)}"
        )
    return True, "OK"


def account_is_reachable() -> tuple[bool, str, str | None]:
    """Lectura REAL del IG configurado: confirma que el token lo alcanza.

    `token_is_valid()` solo mira que el token no haya caducado y tenga el
    scope. NO detecta el enlace IG↔Página roto (error 100/subcode 33), que es
    lo que tuvo el sistema caído en silencio durante días. Aquí se hace un GET
    real de la cuenta y se exige respuesta con `username`.
    """
    if not config.INSTAGRAM_ACCOUNT_ID:
        return False, "Falta INSTAGRAM_ACCOUNT_ID", None
    try:
        info = account_info()
    except Exception as exc:  # noqa: BLE001
        return False, f"No se pudo leer la cuenta IG: {exc}", None
    if "error" in info:
        msg = info["error"].get("message", "Cuenta IG inalcanzable")
        return False, f"Cuenta IG inalcanzable: {msg}", None
    return True, "OK", info.get("username")


def connection_is_healthy() -> tuple[bool, str, str | None]:
    """Health check completo: token válido Y cuenta IG realmente alcanzable.

    Devuelve (ok, mensaje, username). Úsalo en vez de `token_is_valid()` para
    no dar verde cuando la cuenta no es accesible.
    """
    ok, msg = token_is_valid()
    if not ok:
        return False, msg, None
    return account_is_reachable()


def create_container(image_url: str, caption: str) -> str | None:
    """Paso 1: crea el media container. Devuelve container_id o None."""
    with httpx.Client(timeout=40.0) as client:
        resp = client.post(
            f"{GRAPH}/{config.INSTAGRAM_ACCOUNT_ID}/media",
            data={
                "image_url": image_url,
                "caption": caption,
                "access_token": config.INSTAGRAM_ACCESS_TOKEN,
            },
        )
    data = resp.json()
    if "id" in data:
        return data["id"]
    logger.error("[IG] Error creando container: %s", data)
    return None


def _container_status(container_id: str) -> str:
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(
            f"{GRAPH}/{container_id}",
            params={
                "fields": "status_code",
                "access_token": config.INSTAGRAM_ACCESS_TOKEN,
            },
        )
    return resp.json().get("status_code", "UNKNOWN")


def publish(container_id: str) -> tuple[str | None, str]:
    """Paso 2: publica el container. Devuelve (ig_media_id, mensaje)."""
    for _ in range(15):
        status = _container_status(container_id)
        if status == "FINISHED":
            break
        if status == "ERROR":
            return None, "El container quedó en estado ERROR"
        time.sleep(4)
    else:
        return None, "Timeout esperando a que el container esté FINISHED"

    with httpx.Client(timeout=40.0) as client:
        resp = client.post(
            f"{GRAPH}/{config.INSTAGRAM_ACCOUNT_ID}/media_publish",
            data={
                "creation_id": container_id,
                "access_token": config.INSTAGRAM_ACCESS_TOKEN,
            },
        )
    data = resp.json()
    if "id" in data:
        return data["id"], "Publicado"
    return None, f"Error publicando: {data}"


def post_photo(image_url: str, caption: str) -> tuple[str | None, str]:
    """Publica una foto de principio a fin. Devuelve (ig_media_id, mensaje)."""
    container = create_container(image_url, caption)
    if not container:
        return None, "No se pudo crear el container"
    return publish(container)
