"""Tests del material de una noticia: sin artículo, no hay post.

Cada caso es un fallo REAL medido el 22-09-2026 sobre la cola de producción, no
un ejemplo inventado:

  - 179 de 212 noticias (84,4%) llegaban con una URL `news.google.com` que NO
    redirige: responde 200 con una página propia. Nadie la resolvía.
  - 177 de 212 (83,5%) no tenían ni extracto, porque los feeds de Google News
    repiten el titular en la descripción y el agregador lo vacía. Con ese único
    material se escribió el post que confundió a la protagonista de la noticia
    con un homónimo famoso.
  - `fetch_article_text` sobre uno de esos enlaces no "caía al snippet": devolvía
    el texto del BANNER DE COOKIES de Google, que pasa de MIN_CHARS y por eso el
    `or news.summary` del caller nunca saltaba.

Sin red: se inyecta un transporte de httpx, para que toda la lógica real de
httpx (códigos, redirecciones, excepciones) siga corriendo. Los payloads son
literales, grabados de las APIs reales — ver `fixtures/caso_guardiola/`.
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.services import article_extract as ae
from app.services import google_news_url as gnu

FIXTURES = Path(__file__).parent / "fixtures" / "caso_guardiola"

GNEWS_URL = (
    "https://news.google.com/rss/articles/CBMiyAFBVV95cUxOYTd6RGZHX0VCYTFnVGZP"
    "SVhVQ1ZseldYRWlRcnNNZUg4SUJ5c2c1RS1lWV9XaG1oSGtQV2g4VVdzekluWHloLVJzbUdQ"
    "ZTFHUEE0UlZvejB3dnpUQ2FjOVBsMHkxclFYVXBzcGdGQUxFLXNWT21HbDdQdmNaRzE3RGJM"
    "bXk0M192bkliVTNuVVc5QTJFUTdrQ21UbzRLa1dJQ3NnT0dveUFhZEl5WHpNN1FBRVhnZUx2"
    "WGJ4Y1ZENGxTbHkyV2pRag?oc=5"
)
URL_REAL = (
    "http://www.canalextremadura.es/noticias/extremadura/"
    "guardiola-reivindica-el-talento-y-el-lema-inspirado-en-robe-iniesta-en-el-dia"
)

PAGINA_GNEWS = (FIXTURES / "gnews_pagina_fragmento.html").read_text()
RESPUESTA_GNEWS = (FIXTURES / "gnews_batchexecute_respuesta.txt").read_text()
ARTICULO = (FIXTURES / "noticia.txt").read_text()

# Texto REAL que devolvía trafilatura sobre la pantalla de consentimiento: pasa
# de MIN_CHARS y no menciona nada de la noticia. Ese era el bug.
PANTALLA_COOKIES = (
    "Before you continue to Google\n"
    "We use cookies and data to deliver and maintain Google services\n"
    "If you choose to “Accept all,” we will also use cookies and data, "
    "including IP addresses, to develop and improve new services, deliver and "
    "measure the effectiveness of ads, show personalized content and ads.\n"
    "If you choose to “Reject all,” we will not use cookies or IP "
    "addresses for these additional purposes.\n"
    "Select “More options” to see additional information, including "
    "details about managing your privacy settings.\n"
) * 2


@pytest.fixture
def red(monkeypatch):
    """Inyecta un transporte de httpx. Devuelve el registro de peticiones."""
    def _montar(handler):
        vistas: list[httpx.Request] = []

        def _wrapped(request: httpx.Request) -> httpx.Response:
            vistas.append(request)
            return handler(request)

        original = httpx.Client

        def _factory(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(_wrapped)
            return original(*args, **kwargs)

        monkeypatch.setattr(httpx, "Client", _factory)
        return vistas

    return _montar


def _google_ok(request: httpx.Request) -> httpx.Response:
    """Google se comporta como el 22-09-2026: página con firma, luego la URL."""
    if request.url.host == "news.google.com":
        if request.url.path.endswith("/batchexecute"):
            return httpx.Response(200, text=RESPUESTA_GNEWS)
        return httpx.Response(200, text=PAGINA_GNEWS)
    return httpx.Response(200, text=f"<html><body><p>{ARTICULO}</p></body></html>")


# --- Resolución del enlace de Google News ---------------------------------- #
def test_un_enlace_de_google_news_se_traduce_al_medio_real(red):
    red(_google_ok)
    assert gnu.resolve(GNEWS_URL) == URL_REAL


def test_una_url_normal_pasa_de_largo_sin_tocar_la_red(red):
    def _explota(request):  # noqa: ANN001
        raise AssertionError(f"no debería pedir nada: {request.url}")

    red(_explota)
    assert gnu.resolve("https://www.hoy.es/cultura/algo") == "https://www.hoy.es/cultura/algo"


def test_se_manda_la_respuesta_al_banner_de_consentimiento(red):
    """Sin la cookie SOCS, desde una IP europea Google manda a consent.google.com
    y la página que vuelve ya no trae firma. Solo se ve en producción: en un
    portátil suele funcionar igual sin ella, porque el navegador ya respondió al
    banner alguna vez."""
    vistas = red(_google_ok)
    gnu.resolve(GNEWS_URL)
    assert any(
        "SOCS" in (r.headers.get("cookie") or "") for r in vistas
    ), "la petición salió sin la cookie de consentimiento"


def test_si_google_deja_de_dar_firma_no_se_inventa_nada(red):
    red(lambda request: httpx.Response(200, text="<html><body>sin firma</body></html>"))
    assert gnu.resolve(GNEWS_URL) is None


# --- El bug del banner de cookies ------------------------------------------ #
def test_la_pantalla_de_cookies_de_google_no_es_el_articulo(red):
    """El fallo real: `fetch_article_text` devolvía el texto del banner, que pasa
    de MIN_CHARS, así que el `or news.summary` de scrape_news.py:264 nunca
    saltaba y el motor del blog investigaba con la política de cookies dentro."""
    def _google_sin_firma(request: httpx.Request) -> httpx.Response:
        # Google responde, pero con su pantalla: ni firma ni artículo.
        return httpx.Response(200, text=f"<html><body><p>{PANTALLA_COOKIES}</p></body></html>")

    red(_google_sin_firma)
    assert len(PANTALLA_COOKIES) > ae.MIN_CHARS, (
        "si el banner no pasara de MIN_CHARS el test no probaría el bug"
    )
    # Con `resolve_google=False` se reproduce el camino exacto del bug: se
    # descarga news.google.com y se le pasa a trafilatura. Sin este caso el test
    # pasaba por el motivo equivocado — la resolución fallaba antes y la guarda
    # del host nunca llegaba a ejercerse.
    directo = ae.fetch_article(GNEWS_URL, resolve_google=False)
    assert directo.text is None, "el banner de cookies se coló como artículo"
    assert directo.status == ae.UNRESOLVED
    assert ae.fetch_article_text(GNEWS_URL) is None


def test_el_texto_bueno_si_sale(red):
    red(_google_ok)
    texto = ae.fetch_article_text(GNEWS_URL)
    assert texto and "Guardiola" in texto
    assert "Accept all" not in texto


# --- Clasificación del fallo ------------------------------------------------ #
@pytest.mark.parametrize("code", sorted(ae.BOT_BLOCKED))
def test_un_medio_que_no_sirve_a_bots_es_un_no_definitivo(red, code):
    """deia.eus responde 406 a todo lo que no parezca un navegador. Como el UA no
    se disfraza (política del proyecto), reintentar mañana es perder el tiempo:
    la salida es pegar el texto a mano."""
    red(lambda request: httpx.Response(code, text="no"))
    r = ae.fetch_article("https://www.deia.eus/x", resolve_google=False)
    assert r.status == ae.BLOCKED
    assert r.http_code == code
    assert r.definitivo is True
    assert r.text is None


def test_un_articulo_demasiado_corto_no_vale_como_material(red):
    red(lambda request: httpx.Response(200, text="<html><body><p>Cuatro palabras nada más.</p></body></html>"))
    r = ae.fetch_article("https://www.medio.es/x", resolve_google=False)
    assert r.status == ae.PAYWALL_OR_SHORT
    assert r.definitivo is True
    assert not r.ok


def test_una_caida_de_red_si_merece_reintento(red):
    def _cae(request):  # noqa: ANN001
        raise httpx.ConnectError("boom")

    red(_cae)
    r = ae.fetch_article("https://www.medio.es/x", resolve_google=False)
    assert r.status == ae.UNREACHABLE
    assert r.definitivo is False, "una caída de red no puede ser definitiva"


def test_un_enlace_de_google_irresoluble_no_llega_a_pedir_el_articulo(red):
    vistas = red(lambda request: httpx.Response(200, text="<html>sin firma</html>"))
    r = ae.fetch_article(GNEWS_URL)
    assert r.status == ae.UNRESOLVED
    assert r.definitivo is True
    assert all(v.url.host == "news.google.com" for v in vistas), (
        "no se pide el artículo si no se sabe cuál es"
    )


def test_el_caso_348_con_material_ya_dice_quien_es(red):
    """Con el artículo delante, la desambiguación era trivial: el cuerpo trae el
    nombre completo y el cargo. El titular solo decía «Guardiola»."""
    red(_google_ok)
    r = ae.fetch_article(GNEWS_URL)
    assert r.ok
    assert "María Guardiola" in r.text
    assert "presidenta de la Junta de Extremadura" in r.text
    assert r.final_url == URL_REAL
