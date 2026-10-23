"""Ninguna URL con clave puede acabar en el log del cron.

httpx escribe cada petición a nivel INFO con la URL entera, y la API de YouTube
lleva la clave en la query (`key=AIza…`). Pasó en producción (23-10-2026).
"""
from __future__ import annotations

import logging

import httpx

import app  # noqa: F401  (el import es lo que se prueba)


def test_httpx_no_registra_urls_con_el_log_a_nivel_info(caplog):
    logging.basicConfig(level=logging.INFO)
    transporte = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    with caplog.at_level(logging.INFO), httpx.Client(transport=transporte) as http:
        http.get("https://www.googleapis.com/youtube/v3/search?key=AIzaSECRETA")
    assert "AIzaSECRETA" not in caplog.text
