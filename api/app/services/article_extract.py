"""Extracción del cuerpo de un artículo de noticia (efímero, en generación).

El agregador (`scripts/news/aggregate.py`) solo guarda un snippet de 280 chars
(política deliberada tipo Google News: no se persiste el cuerpo ajeno). Eso
dejaba al LLM escribiendo casi a ciegas y los posts salían superficiales.

Aquí, en el momento de reescribir la noticia, descargamos el artículo y
extraemos su texto SOLO como contexto efímero para el LLM (nuestra salida es
una reescritura propia, no se persiste el original). Degradación elegante: si
falla, hay paywall/bloqueo, o el texto es demasiado corto, devolvemos None y
el caller cae al snippet de 280.

Sin herramientas de evasión antibot (sin proxies, headless ni saltar
paywalls): un GET normal con timeout corto. Si la fuente no quiere, no se
fuerza.
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

# Mismo UA que el agregador (navegador real, sin trucos).
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MIN_CHARS = 600  # por debajo de esto no compensa (probable boilerplate/paywall)


def fetch_article_text(
    url: str, *, timeout: float = 20.0, max_chars: int = 8000
) -> str | None:
    """Devuelve el texto principal del artículo, o None si no se puede.

    Usa trafilatura para aislar el cuerpo del boilerplate. No lanza: cualquier
    fallo (red, TLS, bloqueo, extracción pobre) se traduce en None.
    """
    if not url:
        return None
    try:
        import trafilatura
    except Exception:  # noqa: BLE001 — dependencia no instalada todavía
        logger.warning("trafilatura no disponible; se usa el snippet")
        return None

    html = None
    for verify in (True, False):  # fallback TLS como en aggregate._download
        try:
            with httpx.Client(
                timeout=timeout,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
                verify=verify,
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
                html = resp.text
            break
        except Exception as exc:  # noqa: BLE001
            if verify:
                continue
            logger.info("no se pudo descargar %s: %s", url[:80], exc)
            return None
    if not html:
        return None

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
        return None

    if not text or len(text.strip()) < MIN_CHARS:
        return None
    return text.strip()[:max_chars]
