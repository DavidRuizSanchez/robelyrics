"""Resuelve un enlace de Google News a la URL real del medio.

Por qué hace falta: el agregador (`scripts/news/aggregate.py`) bebe sobre todo
de feeds de Google News, y esos feeds NO dan la URL del medio: dan
`news.google.com/rss/articles/CBMi…`, que ya no redirige a ninguna parte —
responde 200 con una página propia—. Medido el 22-09-2026 sobre la cola de
Instagram: **179 de 212 noticias (84,4%) tenían una URL así**. Mientras no se
resuelvan, «descargar el artículo antes de escribir» no es posible para ocho de
cada diez noticias, y lo único que le queda al modelo es el titular. Así se
publicó un homónimo famoso por el sujeto real de la noticia.

Cómo se resuelve: la página del artículo trae una firma (`data-n-a-sg`) y una
marca de tiempo (`data-n-a-ts`); con ellas y el id del artículo se pide la URL
al mismo endpoint que usa la propia web de Google News al abrir el enlace.

Esto NO es evasión antibot y conviene que siga sin serlo: es el endpoint
público que sirve a cualquiera que pulse el enlace, con el User-Agent declarado
del proyecto y sin proxies, sin headless y sin saltarse nada. Si algún día deja
de funcionar, la salida es quedarse sin material (y por tanto sin post), NUNCA
disfrazarse.

La cookie `SOCS` va por lo mismo: desde una IP europea (y el servidor está en
Alemania) Google manda la primera visita a `consent.google.com` y la página que
vuelve ya no trae la firma. `SOCS=CAI` es lo que el propio Google deja puesto
cuando alguien responde al banner de cookies, así que enviarla equivale a haber
respondido — no salta ninguna restricción de acceso. Comprobado desde el
contenedor el 22-09-2026: sin ella el host final es consent.google.com y no hay
firma; con ella se resuelve. Ojo al probar esto desde un portátil: allí suele
funcionar igual sin cookie, porque el navegador ya respondió al banner alguna
vez, y el fallo solo aparece en producción.
"""
from __future__ import annotations

import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

_ENDPOINT = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
# Mismo UA que `article_extract` y el agregador: navegador real, sin trucos.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Respuesta al banner de consentimiento de la UE (ver docstring). Sin esto, la
# primera visita desde una IP europea acaba en consent.google.com.
CONSENT_COOKIES = {"SOCS": "CAI"}

_RE_SG = re.compile(r'data-n-a-sg="([^"]+)"')
_RE_TS = re.compile(r'data-n-a-ts="([^"]+)"')
_RE_ID = re.compile(r'data-n-a-id="([^"]+)"')
# La respuesta viene como JSON escapado dentro de JSON; basta con pescar la
# primera URL que no sea del propio Google.
_RE_URL = re.compile(r'https?://(?!news\.google\.|www\.google\.)[^"\\\s]+')


def _host(url: str) -> str:
    """Host de una URL, para que el log diga dónde acabó la petición."""
    return (url or "").split("//")[-1].split("/")[0]


def is_google_news(url: str) -> bool:
    """¿Es un enlace de Google News (y por tanto hay que resolverlo antes)?"""
    return "news.google.com" in (url or "")


def resolve(url: str, *, timeout: float = 15.0) -> str | None:
    """Devuelve la URL real del medio, o None si no se puede resolver.

    No lanza nunca: cualquier fallo (red, cambio de formato, respuesta rara) se
    traduce en None y el caller decide. Para una URL que no es de Google News
    devuelve la propia URL, para poder llamarla sin comprobar antes.
    """
    if not url:
        return None
    if not is_google_news(url):
        return url

    try:
        with httpx.Client(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            cookies=CONSENT_COOKIES,
        ) as client:
            resp_html = client.get(url)
            html, html_url = resp_html.text, str(resp_html.url)

            sg = _RE_SG.search(html)
            ts = _RE_TS.search(html)
            art = _RE_ID.search(html)
            if not (sg and ts and art):
                logger.info(
                    "[gnews] la página no trae firma (sg=%s ts=%s id=%s, host=%s): %s. "
                    "Si el host es consent.google.com, la cookie de consentimiento "
                    "ha dejado de valer.",
                    bool(sg), bool(ts), bool(art), _host(html_url), url[:70],
                )
                return None

            # Payload que la propia web manda al abrir el enlace.
            inner = json.dumps([
                "garturlreq",
                [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1,
                  None, None, None, None, None, 0, 1],
                 "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
                art.group(1), int(ts.group(1)), sg.group(1),
            ])
            payload = json.dumps([[["Fbv4je", inner, None, "generic"]]])

            resp = client.post(
                _ENDPOINT,
                data={"f.req": payload},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                },
            )
            resp.raise_for_status()
            match = _RE_URL.search(resp.text)
    except Exception as exc:  # noqa: BLE001 — degradación elegante, nunca lanza
        logger.info("[gnews] no se pudo resolver %s: %s", url[:70], exc)
        return None

    if not match:
        logger.info("[gnews] respuesta sin URL para %s", url[:70])
        return None

    real = match.group(0)
    logger.info("[gnews] %s -> %s", url[:50], real[:70])
    return real
