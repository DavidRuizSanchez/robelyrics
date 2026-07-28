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


def _create_media(**fields: str) -> tuple[str | None, str]:
    """POST a /{ig_id}/media con los campos dados. Devuelve (container_id, msg).

    Primitivo común de foto, hijo de carrusel, padre de carrusel y reel: lo único
    que cambia entre ellos son los campos que se mandan.
    """
    with httpx.Client(timeout=40.0) as client:
        resp = client.post(
            f"{GRAPH}/{config.INSTAGRAM_ACCOUNT_ID}/media",
            data={**fields, "access_token": config.INSTAGRAM_ACCESS_TOKEN},
        )
    data = resp.json()
    if "id" in data:
        return data["id"], "OK"
    logger.error("[IG] Error creando container: %s", data)
    return None, str(data.get("error", data))


def create_container(image_url: str, caption: str) -> str | None:
    """Paso 1: crea el media container de una FOTO. Devuelve container_id o None."""
    container, _ = _create_media(image_url=image_url, caption=caption)
    return container


def _container_status(container_id: str) -> tuple[str, str]:
    """(status_code, detalle). El detalle explica POR QUÉ falló un container.

    Antes solo se leía `status_code`, así que un ERROR llegaba al panel como
    "quedó en estado ERROR" y sin causa. Con vídeo eso es inasumible.
    """
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(
            f"{GRAPH}/{container_id}",
            params={
                "fields": "status_code,status",
                "access_token": config.INSTAGRAM_ACCESS_TOKEN,
            },
        )
    data = resp.json()
    return data.get("status_code", "UNKNOWN"), data.get("status", "")


def _wait_finished(
    container_id: str, attempts: int = 15, interval: float = 4.0
) -> tuple[bool, str]:
    """Espera a que un container esté listo para publicar."""
    for _ in range(attempts):
        status, detalle = _container_status(container_id)
        if status == "FINISHED":
            return True, "OK"
        if status in ("ERROR", "EXPIRED"):
            return False, f"container en estado {status}: {detalle or 'sin detalle'}"
        if status == "PUBLISHED":
            return True, "ya publicado"
        time.sleep(interval)
    return False, "Timeout esperando a que el container esté FINISHED"


def publish(
    container_id: str, attempts: int = 15, interval: float = 4.0
) -> tuple[str | None, str]:
    """Paso 2: publica el container. Devuelve (ig_media_id, mensaje)."""
    listo, msg = _wait_finished(container_id, attempts=attempts, interval=interval)
    if not listo:
        return None, msg

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


# --------------------------------------------------------------------------- #
# Carrusel
# --------------------------------------------------------------------------- #
MIN_CAROUSEL_ITEMS = 2
MAX_CAROUSEL_ITEMS = 10


def create_carousel_item(media_url: str, is_video: bool = False) -> tuple[str | None, str]:
    """Container HIJO de un carrusel. OJO: los hijos NO llevan caption."""
    campos: dict = {"is_carousel_item": "true"}
    if is_video:
        campos["video_url"] = media_url
        campos["media_type"] = "VIDEO"
    else:
        campos["image_url"] = media_url
    return _create_media(**campos)


def create_carousel_container(children: list[str], caption: str) -> tuple[str | None, str]:
    """Container PADRE. El caption va SOLO aquí, nunca en los hijos."""
    return _create_media(
        media_type="CAROUSEL", children=",".join(children), caption=caption
    )


def post_carousel(media_urls: list[str], caption: str) -> tuple[str | None, str]:
    """Publica un carrusel de 2-10 imágenes. Devuelve (ig_media_id, mensaje).

    Si un hijo falla, se aborta sin crear el padre: mejor no publicar que
    publicar un carrusel mutilado. Los containers huérfanos caducan solos a las
    24 h, así que no hay que limpiarlos.
    """
    n = len(media_urls)
    if not (MIN_CAROUSEL_ITEMS <= n <= MAX_CAROUSEL_ITEMS):
        return None, f"un carrusel admite entre {MIN_CAROUSEL_ITEMS} y {MAX_CAROUSEL_ITEMS} elementos, no {n}"

    hijos: list[str] = []
    for i, url in enumerate(media_urls, start=1):
        hijo, msg = create_carousel_item(url)
        if not hijo:
            return None, f"hijo {i}/{n}: {msg}"
        # Cada hijo debe estar FINISHED antes de montar el padre; si no, el
        # padre falla con un error genérico imposible de diagnosticar.
        listo, msg = _wait_finished(hijo, attempts=8, interval=2.0)
        if not listo:
            return None, f"hijo {i}/{n}: {msg}"
        hijos.append(hijo)

    padre, msg = create_carousel_container(hijos, caption)
    if not padre:
        return None, f"container padre: {msg}"
    return publish(padre)


def post_photo(image_url: str, caption: str) -> tuple[str | None, str]:
    """Publica una foto de principio a fin. Devuelve (ig_media_id, mensaje)."""
    container = create_container(image_url, caption)
    if not container:
        return None, "No se pudo crear el container"
    return publish(container)


# --------------------------------------------------------------------------- #
# Insights propios — la única forma de saber si un cambio funciona
# --------------------------------------------------------------------------- #
# Requiere el permiso `instagram_manage_insights`, que NO estaba en el token
# generado en su día (ver infra/META_RECONNECT.md). Sin él, estas funciones
# devuelven el error de la API en vez de números inventados.
MEDIA_METRICS = "reach,saved,shares,comments,likes,total_interactions"


def media_insights(ig_media_id: str) -> tuple[dict | None, str]:
    """Métricas de UNA publicación nuestra. Devuelve (metricas, mensaje).

    `saved` y `shares` son las señales de calidad de verdad: un like es barato,
    guardar un post no.
    """
    if not config.INSTAGRAM_ACCESS_TOKEN:
        return None, "Falta INSTAGRAM_ACCESS_TOKEN"
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(
            f"{GRAPH}/{ig_media_id}/insights",
            params={
                "metric": MEDIA_METRICS,
                "access_token": config.INSTAGRAM_ACCESS_TOKEN,
            },
        )
    data = resp.json()
    if "error" in data:
        err = data["error"]
        return None, f'{err.get("message", "error")} (code={err.get("code")})'
    metricas = {
        d.get("name"): (d.get("values") or [{}])[0].get("value")
        for d in data.get("data", [])
    }
    return metricas, "OK"


def account_insights(period: str = "day") -> tuple[dict | None, str]:
    """Métricas de la CUENTA (alcance, visitas al perfil, seguidores)."""
    if not config.INSTAGRAM_ACCOUNT_ID:
        return None, "Falta INSTAGRAM_ACCOUNT_ID"
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(
            f"{GRAPH}/{config.INSTAGRAM_ACCOUNT_ID}/insights",
            params={
                "metric": "reach,profile_views,follower_count",
                "period": period,
                "access_token": config.INSTAGRAM_ACCESS_TOKEN,
            },
        )
    data = resp.json()
    if "error" in data:
        err = data["error"]
        return None, f'{err.get("message", "error")} (code={err.get("code")})'
    return {
        d.get("name"): (d.get("values") or [{}])[0].get("value")
        for d in data.get("data", [])
    }, "OK"


# --------------------------------------------------------------------------- #
# Comentarios — el motor de comunidad
# --------------------------------------------------------------------------- #
# Requiere `instagram_manage_comments`. Las tres cuentas del nicho con mejor
# engagement se autocomentan el post para arrancar el hilo; aquí está la pieza
# que lo permite hacer igual.
def comment_on_media(ig_media_id: str, texto: str) -> tuple[str | None, str]:
    """Publica un comentario en una publicación NUESTRA."""
    if not texto.strip():
        return None, "comentario vacío"
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(
            f"{GRAPH}/{ig_media_id}/comments",
            data={
                "message": texto[:2200],
                "access_token": config.INSTAGRAM_ACCESS_TOKEN,
            },
        )
    data = resp.json()
    if "id" in data:
        return data["id"], "Comentado"
    return None, str(data.get("error", data))


def list_comments(ig_media_id: str, limit: int = 50) -> tuple[list[dict], str]:
    """Comentarios de una publicación nuestra, para la bandeja del panel."""
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(
            f"{GRAPH}/{ig_media_id}/comments",
            params={
                "fields": "id,text,username,timestamp,replies{id}",
                "limit": limit,
                "access_token": config.INSTAGRAM_ACCESS_TOKEN,
            },
        )
    data = resp.json()
    if "error" in data:
        return [], str(data["error"])
    return list(data.get("data") or []), "OK"


def reply_to_comment(comment_id: str, texto: str) -> tuple[str | None, str]:
    """Responde a un comentario concreto."""
    with httpx.Client(timeout=20.0) as client:
        resp = client.post(
            f"{GRAPH}/{comment_id}/replies",
            data={
                "message": texto[:2200],
                "access_token": config.INSTAGRAM_ACCESS_TOKEN,
            },
        )
    data = resp.json()
    if "id" in data:
        return data["id"], "Respondido"
    return None, str(data.get("error", data))
