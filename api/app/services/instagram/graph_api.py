"""Cliente de la Instagram Graph API (publicación de fotos).

Flujo oficial en 2 pasos: crear el container de media → publicar el container.
Docs: https://developers.facebook.com/docs/instagram-platform/content-publishing
"""
from __future__ import annotations

import logging
import time

import httpx

from app.services.instagram import config
from app.services.instagram.errors import MetaError

logger = logging.getLogger(__name__)

# La Graph API pide el token en la QUERY STRING, y httpx registra cada petición
# con la URL entera: el `INSTAGRAM_ACCESS_TOKEN` acababa en claro en
# /var/log/robelyrics-cron.log (8,4 MB, cada 15 minutos, y es un token de System
# User que NO caduca y puede publicar). Cuatro scripts sueltos ya silenciaban
# httpx a mano; se hace aquí porque es el único sitio por el que pasan todas las
# llamadas —cron, panel y consola— y así no depende de que nadie se acuerde.
logging.getLogger("httpx").setLevel(logging.WARNING)

GRAPH = "https://graph.facebook.com/v21.0"

# Lo que devuelven estas funciones como "motivo": texto cuando es cosa nuestra,
# `MetaError` cuando lo dijo Meta (y entonces trae code/subcode para clasificar).
Motivo = str | MetaError


def account_info() -> dict:
    """Devuelve info de la cuenta IG (para verificar el token)."""
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(
            f"{GRAPH}/{config.INSTAGRAM_ACCOUNT_ID}",
            params={
                # NO añadir aquí `content_publishing_limit`: como campo anidado
                # Meta responde 500 («An unknown error has occurred», code 1) y
                # tumba el health check entero. Solo existe como edge aparte
                # (`/{ig-id}/content_publishing_limit`), y no compensa una
                # petición extra por publicación: la cuota agotada llega como
                # `9/2207042` y `errors` ya la clasifica como global.
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


def _create_media(**fields: str) -> tuple[str | None, Motivo]:
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
    return None, MetaError.desde(data)


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
) -> tuple[bool, Motivo]:
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
) -> tuple[str | None, Motivo]:
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
    return None, MetaError.desde(data)


# --------------------------------------------------------------------------- #
# Carrusel
# --------------------------------------------------------------------------- #
def _prefijar(msg, prefijo: str):
    """Antepone contexto SIN perder el código de Meta.

    Un `f"hijo {i}/{n}: {msg}"` convierte el MetaError en texto plano y con él
    se va el 25/2207050 que dice que la cuenta está restringida: el post acaba
    quemando un intento por un fallo que no era suyo. Pasa siempre por aquí.
    """
    if isinstance(msg, MetaError):
        return msg.con_prefijo(prefijo)
    return f"{prefijo}: {msg}"


MIN_CAROUSEL_ITEMS = 2
MAX_CAROUSEL_ITEMS = 10


def create_carousel_item(media_url: str, is_video: bool = False) -> tuple[str | None, Motivo]:
    """Container HIJO de un carrusel. OJO: los hijos NO llevan caption."""
    campos: dict = {"is_carousel_item": "true"}
    if is_video:
        campos["video_url"] = media_url
        campos["media_type"] = "VIDEO"
    else:
        campos["image_url"] = media_url
    return _create_media(**campos)


def create_carousel_container(children: list[str], caption: str) -> tuple[str | None, Motivo]:
    """Container PADRE. El caption va SOLO aquí, nunca en los hijos."""
    return _create_media(
        media_type="CAROUSEL", children=",".join(children), caption=caption
    )


def post_carousel(media_urls: list[str], caption: str) -> tuple[str | None, Motivo]:
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
            return None, _prefijar(msg, f"hijo {i}/{n}")
        # Cada hijo debe estar FINISHED antes de montar el padre; si no, el
        # padre falla con un error genérico imposible de diagnosticar.
        listo, msg = _wait_finished(hijo, attempts=8, interval=2.0)
        if not listo:
            return None, _prefijar(msg, f"hijo {i}/{n}")
        hijos.append(hijo)

    padre, msg = create_carousel_container(hijos, caption)
    if not padre:
        return None, _prefijar(msg, "container padre")
    return publish(padre)


def post_photo(image_url: str, caption: str) -> tuple[str | None, Motivo]:
    """Publica una foto de principio a fin. Devuelve (ig_media_id, mensaje)."""
    container, msg = _create_media(image_url=image_url, caption=caption)
    if not container:
        # Antes esto pasaba por un `create_container` que se comía el motivo y
        # devolvía "No se pudo crear el container" a secas: el error de Meta que
        # explicaba POR QUÉ (y con él su código) no llegaba a la BD. Ese wrapper
        # ya no existe; era su único usuario.
        return None, msg
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


# --------------------------------------------------------------------------- #
# Reels
# --------------------------------------------------------------------------- #
# El procesado de vídeo de Meta tarda de 30 s a varios minutos, así que el
# polling es mucho más largo que el de una foto (15×4 s = 60 s daría timeout casi
# siempre). OJO: eso NO cabe dentro de una petición del panel — Cloudflare corta
# a los 100 s y el proyecto ya se comió un 524 por esto. Los reels se publican
# desde el cron; el panel solo prepara.
REELS_POLL_ATTEMPTS = 60
REELS_POLL_INTERVAL = 10.0


def create_reel_container(
    video_url: str, caption: str, cover_url: str | None = None,
    share_to_feed: bool = True,
) -> tuple[str | None, str]:
    """Container de un reel a partir de una URL de vídeo pública."""
    campos = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true" if share_to_feed else "false",
    }
    if cover_url:
        campos["cover_url"] = cover_url
    return _create_media(**campos)


def post_reel(
    video_url: str, caption: str, cover_url: str | None = None
) -> tuple[str | None, str]:
    """Publica un reel de principio a fin. Devuelve (ig_media_id, mensaje)."""
    container, msg = create_reel_container(video_url, caption, cover_url=cover_url)
    if not container:
        return None, msg
    return publish(
        container, attempts=REELS_POLL_ATTEMPTS, interval=REELS_POLL_INTERVAL
    )
