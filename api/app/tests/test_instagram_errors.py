"""De quién es la culpa cuando Meta dice que no.

En agosto de 2026 Meta restringió la cuenta (`code 25 / subcode 2207050`) y el
pipeline trató ese bloqueo GLOBAL como si fuera culpa de cada post: les quemó
los tres intentos y 47 se quedaron fuera de la cola para siempre. Estos tests
fijan la distinción para que no se pierda otra vez.
"""
from __future__ import annotations

import pytest

from app.services.instagram import errors
from app.services.instagram.errors import MetaError

# El payload literal que devolvió Meta durante el incidente.
CUENTA_RESTRINGIDA = {
    "error": {
        "message": "User access is restricted",
        "type": "OAuthException",
        "code": 25,
        "error_subcode": 2207050,
        "is_transient": False,
        "error_user_title": "El usuario está restringido",
        "error_user_msg": "La cuenta de Instagram está restringida.",
        "fbtrace_id": "ACjuZHyWFsoabxb_RFa1dVm",
    }
}


def test_cuenta_restringida_no_gasta_intento():
    """EL test de regresión del incidente: 47 posts murieron por esto."""
    err = MetaError.desde(CUENTA_RESTRINGIDA)
    assert err.code == 25
    assert err.subcode == 2207050
    assert err.etiqueta == "25/2207050"
    assert errors.es_global(err)
    assert not errors.quema_intento(err)


@pytest.mark.parametrize(
    "code, subcode",
    [
        (190, None),      # token caducado
        (4, None),        # límite de peticiones de la app
        (17, None),       # límite del usuario
        (32, None),       # límite de la página
        (613, None),      # demasiadas llamadas por segundo
        (9, 2207042),     # límite de 25 publicaciones/24 h
        (368, None),      # bloqueado temporalmente por políticas
        (200, None),      # permiso ausente
        (299, None),      # (el otro extremo del rango de permisos)
        (2, None),        # servicio de Meta caído
        (100, 33),        # enlace IG↔Página roto
        (4, 2207051),     # restricción antispam de la cuenta
    ],
)
def test_los_fallos_globales_no_gastan_intento(code, subcode):
    err = MetaError("da igual el texto", code=code, subcode=subcode)
    assert errors.es_global(err)
    assert not errors.quema_intento(err)


@pytest.mark.parametrize(
    "code, subcode",
    [
        (36004, 2207010),  # caption de más de 2200 caracteres
        (36003, 2207009),  # aspect ratio fuera de rango
        (9004, 2207052),   # su media no se pudo descargar
        (36000, 2207004),  # imagen de más de 8 MiB
        (100, 2207028),    # carrusel fuera de 2-10 elementos
        (24, 2207008),     # su container caducó
        (506, None),       # publicación duplicada
    ],
)
def test_los_fallos_del_item_si_gastan_intento(code, subcode):
    err = MetaError("da igual el texto", code=code, subcode=subcode)
    assert not errors.es_global(err)
    assert errors.quema_intento(err)


def test_is_transient_manda_sobre_el_codigo():
    """Si Meta dice que es pasajero, reintentar tiene sentido: no se quema."""
    err = MetaError("vuelve más tarde", code=99999, transient=True)
    assert errors.es_global(err)


def test_un_subcodigo_conocido_manda_sobre_is_transient():
    """Lo explícito gana a la heurística: su imagen pesa de más ahora y dentro
    de una hora, por mucho que Meta lo marque como transitorio."""
    err = MetaError("imagen enorme", code=36000, subcode=2207004, transient=True)
    assert not errors.es_global(err)
    assert errors.quema_intento(err)


def test_un_codigo_desconocido_gasta_intento():
    """Decisión deliberada, no descuido: no gastarlo dejaría la cola parada para
    siempre detrás del mismo item, que es el fallo silencioso. El riesgo de que
    un GLOBAL nuevo condene la cola lo tapa el cortacircuitos por racha."""
    err = MetaError("algo que Meta no había dicho nunca", code=424242)
    assert not errors.es_global(err)
    assert errors.quema_intento(err)


def test_un_fallo_sin_codigo_gasta_intento():
    """Cloudinary, un fichero que falta: no viene de Meta, es material del item."""
    assert errors.quema_intento("Cloudinary: connection reset")
    assert not errors.es_global("Cloudinary: connection reset")


def test_el_prefijo_del_carrusel_conserva_el_codigo():
    """`post_carousel` reetiquetaba con un f-string y ahí se perdía el 25: el
    post acababa quemando un intento por un bloqueo que no era suyo."""
    err = MetaError.desde(CUENTA_RESTRINGIDA).con_prefijo("hijo 1/5")
    assert str(err).startswith("hijo 1/5: User access is restricted")
    assert err.code == 25
    assert err.subcode == 2207050
    assert not errors.quema_intento(err)


def test_el_mensaje_se_lee_como_texto():
    """Aguas abajo se hace `str(motivo)[:2000]` y se interpola en logs."""
    err = MetaError.desde(CUENTA_RESTRINGIDA)
    assert str(err) == "User access is restricted"
    assert f"{err}" == "User access is restricted"
    assert str(err)[:4] == "User"


def test_desde_acepta_el_error_suelto_y_el_sobre():
    """`_create_media` recibe el sobre entero; `publish`, a veces el error solo."""
    a = MetaError.desde(CUENTA_RESTRINGIDA)
    b = MetaError.desde(CUENTA_RESTRINGIDA["error"])
    assert (a.code, a.subcode) == (b.code, b.subcode) == (25, 2207050)


def test_una_respuesta_rara_no_revienta():
    """Si Meta contesta algo inesperado, se guarda como texto y se clasifica
    como desconocido: nunca una excepción dentro del camino de publicación."""
    err = MetaError.desde({"lo que sea": 1})
    assert err.code is None
    assert err.etiqueta is None
    assert errors.quema_intento(err)
