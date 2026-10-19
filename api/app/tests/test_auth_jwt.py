"""La validación de los JWT no se afloja al cambiar de librería.

Se migró de python-jose (abandonada; GHSA-3qf3-8w2g-rqmx sin parche) a PyJWT.
Los tokens firman las sesiones del panel y los botones de los correos
(aprobar/publicar), así que un token alterado, sin firma o caducado tiene que
seguir cayendo.
"""
from __future__ import annotations

import time

import jwt

from app.config import get_settings
from app.services.auth import create_access_token, decode_token


def test_un_token_propio_se_valida():
    assert decode_token(create_access_token(7))["sub"] == "7"


def test_firma_alterada_se_rechaza():
    t = create_access_token(7)
    assert decode_token(t[:-4] + ("AAAA" if not t.endswith("AAAA") else "BBBB")) is None


def test_algoritmo_none_se_rechaza():
    sin_firma = jwt.encode({"sub": "1", "exp": int(time.time()) + 60}, key=None, algorithm="none")
    assert decode_token(sin_firma) is None


def test_otro_secreto_se_rechaza():
    ajeno = jwt.encode({"sub": "1", "exp": int(time.time()) + 60}, "otro-secreto-cualquiera",
                       algorithm=get_settings().jwt_algo)
    assert decode_token(ajeno) is None


def test_caducado_se_rechaza():
    s = get_settings()
    viejo = jwt.encode({"sub": "1", "exp": int(time.time()) - 10}, s.jwt_secret,
                       algorithm=s.jwt_algo)
    assert decode_token(viejo) is None
