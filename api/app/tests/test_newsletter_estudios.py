"""El digest semanal tiene que llevar los estudios, y llevarlos UNA vez.

Un estudio no es una fila de `posts`, así que `posts_pending_for_subscriber` no lo
veía y el digest no lo mandaba nunca: el estudio del repertorio en directo solo
viajaba como un enlace dentro del cuerpo de un post, y el correo manda título y
excerpt, no el cuerpo. Con 17 suscriptores eso era el 100% del alcance por email
perdido.

Lo que se vigila aquí es lo que puede volver a romperse: que se seleccione por el
mismo criterio por suscriptor que los posts (y por tanto no se repita), que un
estudio dispare envío aunque no haya entradas, y que el asunto nombre lo que va
dentro.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.services import estudios as mod
from app.services.email import render_newsletter_digest_email
from app.services.estudios import Estudio, pendientes_desde

UNO = Estudio(
    slug="uno",
    titulo="El estudio de prueba",
    resumen="Un resumen.",
    publicado=date(2026, 10, 7),
)


@pytest.fixture
def solo_uno(monkeypatch):
    monkeypatch.setattr(mod, "ESTUDIOS", (UNO,))
    return UNO


def test_entra_si_se_publico_despues_del_ultimo_envio(solo_uno):
    envio_anterior = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
    assert pendientes_desde(envio_anterior) == [UNO]


def test_no_se_repite_en_el_envio_siguiente(solo_uno):
    # El domingo de después: el estudio ya se anunció y no vuelve.
    envio_posterior = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
    assert pendientes_desde(envio_posterior) == []


def test_el_dia_exacto_del_envio_no_lo_duplica(solo_uno):
    # `publicado_utc` es medianoche, así que un envío del mismo día a las 12:00 lo
    # incluye una vez y el de la semana siguiente ya no.
    assert pendientes_desde(datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)) == []
    assert pendientes_desde(datetime(2026, 10, 6, 23, 59, tzinfo=timezone.utc)) == [UNO]


def test_un_suscriptor_nuevo_recibe_todos(solo_uno):
    # `last_sent_at` a None: acaba de confirmar y no se ha perdido nada.
    assert pendientes_desde(None) == [UNO]


def _render(posts, estudios):
    return render_newsletter_digest_email(
        posts, "https://x/baja?token=t", "https://entreinteriores.com", estudios=estudios
    )


def _estudio_dict():
    return {
        "title": UNO.titulo,
        "excerpt": UNO.resumen,
        "url": "https://entreinteriores.com/estudios/uno",
        "published_at_human": "7 de octubre de 2026",
    }


def test_el_html_y_el_texto_llevan_el_estudio():
    html, text = _render([], [_estudio_dict()])
    assert "/estudios/uno" in html
    assert "ver el estudio" in html
    assert "datos propios" in html
    # El texto plano también: hay clientes que solo leen esa parte.
    assert "/estudios/uno" in text
    assert "DATOS PROPIOS" in text


def test_sin_estudios_el_correo_no_cambia():
    # Compatibilidad: quien llame con tres argumentos tiene que seguir funcionando
    # y el correo no puede traer una sección vacía.
    post = {
        "title": "Una entrada",
        "excerpt": "x",
        "url": "https://entreinteriores.com/blog/x",
        "kind_label": "Editorial",
        "published_at_human": "7 de octubre de 2026",
    }
    con_kwarg, _ = _render([post], [])
    sin_kwarg, _ = render_newsletter_digest_email(
        [post], "https://x/baja?token=t", "https://entreinteriores.com"
    )
    assert con_kwarg == sin_kwarg
    assert "datos propios" not in con_kwarg
    assert "Una nueva entrada" in con_kwarg


def test_el_titular_nombra_lo_que_va_dentro():
    solo_estudio, _ = _render([], [_estudio_dict()])
    assert "Un estudio nuevo" in solo_estudio

    post = {
        "title": "Una entrada", "excerpt": "x",
        "url": "https://entreinteriores.com/blog/x",
        "kind_label": "Editorial", "published_at_human": "7 de octubre de 2026",
    }
    mezcla, _ = _render([post], [_estudio_dict()])
    assert "Una entrada nueva y un estudio" in mezcla


def test_el_estudio_real_esta_dado_de_alta():
    # Si alguien lo saca de la lista del backend, el enlace del post se desenlaza
    # y la newsletter deja de anunciarlo: las dos cosas en silencio.
    slugs = {e.slug for e in mod.ESTUDIOS}
    assert "repertorio-en-directo-extremoduro-robe" in slugs
