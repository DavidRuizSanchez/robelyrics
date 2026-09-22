"""Extracción del cuerpo de un artículo de noticia.

El agregador (`scripts/news/aggregate.py`) guardaba solo un snippet de 280
chars. Eso dejaba al LLM escribiendo casi a ciegas: medido el 22-09-2026 sobre
la cola de Instagram, **177 de 212 noticias (83,5%) ni siquiera tenían snippet**
—los feeds de Google News repiten el titular en la descripción y el agregador lo
vacía—, así que el modelo escribía cuatro frases, elegía foto y montaba un
carrusel a partir de UNA línea. De ahí salió un post que confundió a la
protagonista con un homónimo famoso y le atribuyó una afinidad que ninguna
fuente mencionaba.

Desde entonces el cuerpo SÍ se persiste (`news_items.body_text`), con la vida
corta de esa tabla (`purge_old` la purga a los 7 días): es caché de trabajo, no
archivo. Lo que sobrevive de un artículo ajeno sigue siendo titular, enlace y
extracto — el snapshot de `instagram_queue` no copia el cuerpo.

`fetch_article` dice además POR QUÉ falla, que es lo que permite distinguir «el
medio bloquea bots» (definitivo: la salida es pegar el texto a mano) de «se cayó
la red» (transitorio: se reintenta mañana).

Sin herramientas de evasión antibot (sin proxies, headless ni saltar paywalls):
un GET normal con timeout corto. Si la fuente no quiere, no se fuerza.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.services import google_news_url

logger = logging.getLogger(__name__)

# Mismo UA que el agregador (navegador real, sin trucos).
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# Códigos con los que un medio dice "no sirvo a bots". Nuestro UA no se
# disfraza (Responsible Builder Policy), así que estos son un NO definitivo, no
# un fallo transitorio: la salida es pegar el texto a mano. Caso real: el WAF de
# deia.eus responde 406 a todo lo que no parezca un navegador, hasta a su propio
# robots.txt. Viven aquí, en el módulo de más abajo, y `url_ingest` los importa:
# antes estaban allí y traerlos al revés arrastraba SQLAlchemy y scripts dentro
# de un módulo que solo necesita httpx.
BOT_BLOCKED = {401, 403, 406, 429, 451}
PASTE_HINT = (
    "abre el artículo en el navegador, copia el texto y pégalo en "
    "«cuerpo del artículo»"
)

MIN_CHARS = 350  # por debajo: probable boilerplate/paywall. Más tolerante que
# antes (600) para no descartar artículos cortos de medios pequeños; el caller
# cae al snippet y research_and_write investiga el tema igualmente.

# Estados de `ArticleFetch.status`. Los tres primeros son definitivos (no tiene
# sentido reintentarlos mañana); `unreachable` sí es transitorio.
OK = "ok"
BLOCKED = "blocked"                    # el medio responde 401/403/406/429/451
PAYWALL_OR_SHORT = "paywall_or_short"  # descarga, pero no hay cuerpo que valga
UNRESOLVED = "unresolved"              # enlace de Google News que no se resuelve
UNREACHABLE = "unreachable"            # red, TLS, timeout, 5xx
NO_EXTRACTOR = "no_extractor"          # trafilatura no instalada

DEFINITIVOS = {BLOCKED, PAYWALL_OR_SHORT, UNRESOLVED}


@dataclass(frozen=True)
class ArticleFetch:
    """Resultado de intentar bajar un artículo. Nunca lanza; siempre informa."""

    text: str | None
    status: str
    http_code: int | None = None
    chars: int = 0
    final_url: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == OK and bool(self.text)

    @property
    def definitivo(self) -> bool:
        """¿Reintentarlo mañana sería perder el tiempo?"""
        return self.status in DEFINITIVOS


def fetch_article(
    url: str,
    *,
    timeout: float = 20.0,
    max_chars: int = 8000,
    resolve_google: bool = True,
) -> ArticleFetch:
    """Descarga y extrae el cuerpo de un artículo, diciendo por qué falla.

    `resolve_google` traduce antes los enlaces `news.google.com`, que no
    redirigen y son la mayoría de lo que entra por los feeds.
    """
    if not url:
        return ArticleFetch(None, UNREACHABLE)

    if resolve_google and google_news_url.is_google_news(url):
        real = google_news_url.resolve(url, timeout=min(timeout, 15.0))
        if not real:
            return ArticleFetch(None, UNRESOLVED, final_url=None)
        url = real

    try:
        import trafilatura
    except Exception:  # noqa: BLE001 — dependencia no instalada todavía
        logger.warning("trafilatura no disponible; se usa el snippet")
        return ArticleFetch(None, NO_EXTRACTOR, final_url=url)

    html = None
    code: int | None = None
    for verify in (True, False):  # fallback TLS como en aggregate._download
        try:
            with httpx.Client(
                timeout=timeout,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                verify=verify,
            ) as client:
                resp = client.get(url)
                code = resp.status_code
                # Un "no sirvo a bots" es definitivo: no se reintenta ni se
                # disfraza el UA; la salida es pegar el texto a mano.
                if code in BOT_BLOCKED:
                    logger.info("%s bloquea bots (HTTP %s)", url[:80], code)
                    return ArticleFetch(None, BLOCKED, code, final_url=url)
                resp.raise_for_status()
                html = resp.text
            break
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code in BOT_BLOCKED:
                return ArticleFetch(None, BLOCKED, code, final_url=url)
            logger.info("no se pudo descargar %s: HTTP %s", url[:80], code)
            return ArticleFetch(None, UNREACHABLE, code, final_url=url)
        except Exception as exc:  # noqa: BLE001
            if verify:
                continue
            logger.info("no se pudo descargar %s: %s", url[:80], exc)
            return ArticleFetch(None, UNREACHABLE, code, final_url=url)
    if not html:
        return ArticleFetch(None, UNREACHABLE, code, final_url=url)

    # Si después de todo seguimos en Google, lo que hay delante es su pantalla
    # de consentimiento, no el artículo. Y trafilatura la extrae tan campante:
    # pasa de MIN_CHARS, así que el `or news.summary` del caller NUNCA saltaba y
    # el motor del blog se puso a investigar noticias con la política de cookies
    # de Google como cuerpo. Medido el 22-09-2026.
    host_final = (url or "").split("//")[-1].split("/")[0]
    if host_final.endswith("google.com"):
        logger.info("[articulo] %s sigue en Google: no es el artículo", host_final)
        return ArticleFetch(None, UNRESOLVED, code, final_url=url)

    try:
        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
            url=url,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("extracción falló para %s: %s", url[:80], exc)
        return ArticleFetch(None, PAYWALL_OR_SHORT, code, final_url=url)

    n = len(text.strip()) if text else 0
    if n < MIN_CHARS:
        logger.info(
            "texto corto (%d<%d) para %s — caigo al snippet", n, MIN_CHARS, url[:80]
        )
        return ArticleFetch(None, PAYWALL_OR_SHORT, code, n, final_url=url)
    limpio = text.strip()[:max_chars]
    return ArticleFetch(limpio, OK, code, len(limpio), final_url=url)


def fetch_article_text(
    url: str, *, timeout: float = 20.0, max_chars: int = 8000
) -> str | None:
    """Devuelve el texto principal del artículo, o None si no se puede.

    SÍ resuelve los enlaces de Google News. Antes no, con la idea de que el
    caller "caería al snippet"; pero no caía: la página de Google pasa de
    MIN_CHARS y sus consumidores (`scrape_news.py:264`, `regen_one_post.py`)
    daban por bueno el texto del banner de cookies. Preservar aquel contrato era
    preservar el bug.
    """
    return fetch_article(url, timeout=timeout, max_chars=max_chars).text
