"""Titles y headings v2 (12-11-2026): lo que la guarda del 11-11 dejó pasar.

El crawl del 12-11 de las 388 URLs encontró titles publicados que nunca entraron
en la pasada porque la guarda los dio por buenos. Son literales de prod: si alguno
vuelve a pasar, la guarda está mal. Y los textos de David siguen pasando.
"""
from __future__ import annotations

import pytest

from app.services import seo_style

MALOS_REALES = [
    "Bilbao y Extremoduro: Iñaki 'Uoho' Antón transforma",
    "Pamplona impulsa a Extremoduro y Robe en solitario",
    "Amistad y tribu en Extremoduro: Robe y la conexión",
    "Antimilitarismo y paz en Extremoduro: crítica",
    "La hoguera, el fuego, la mecha en Extremoduro: símbolo",
    "Fugacidad y tiempo en Extremoduro: Robe y su obsesión",
    "Paso del tiempo en Extremoduro: Robe y su obra",
    "Badajoz en Extremoduro: la crítica de 'Extremaydura'",
    "Robe: 'Donde se rompen las olas' y su simbolismo",
    "Ama, ama, ama y ensancha el alma de Extremoduro: amor",
]

BUENOS = [
    "Barricada: miembros, historia y legado del grupo de rock español",  # David
    "La Plasencia de Robe: cuna de Extremoduro",                         # David
    "Letra de Desarraigo - Extremoduro",                                 # David
    "El bar en Extremoduro: letras, refugio y Simetría",
    "Luis von Fanta en Extremoduro: de Los Dogos a «Deltoya»",
    "La ley innata, disco de 2008",
]


@pytest.mark.parametrize("title", MALOS_REALES)
def test_los_titles_que_se_colaron_caen(title):
    assert seo_style.estructura(title) or seo_style.formulas_vacias(title), title


@pytest.mark.parametrize("title", BUENOS)
def test_los_buenos_siguen_pasando(title):
    assert not seo_style.estructura(title) and not seo_style.formulas_vacias(title), title


def test_el_title_verdict_bloquea_la_estructura():
    v = seo_style.title_verdict("Antimilitarismo y paz en Extremoduro: crítica",
                                body_md="Extremoduro y la crítica antimilitarista.",
                                subject="Antimilitarismo", entity_type="theme")
    assert not v.ok and any("dos puntos" in m for m in v.motivos)


# --- Headings del blog, que nadie había repasado -----------------------------
H2_BLOG_MALOS = [
    "El Significado de la Letra de «Decidí» de Extremoduro",
    "Contexto y Grabación de 'Rock Transgresivo'",
    "El Viaje Íntimo de la Locura: Su Incursión Literaria",
    "Marte como Metáfora de Huida en la Canción 'Extraterrestre'",
]


@pytest.mark.parametrize("h", H2_BLOG_MALOS)
def test_los_h2_del_blog_caen(h):
    assert not seo_style.heading_verdict([h], subject="").ok, h


def test_sin_sujeto_no_se_exige_nombrarlo():
    v = seo_style.heading_verdict(["Cómo se grabó", "Qué cuenta la letra"], subject="")
    assert v.ok, v.motivos


def test_una_mayuscula_tras_los_dos_puntos_sigue_siendo_aviso():
    v = seo_style.heading_verdict(["Su obra: Análisis de la letra"], subject="Otro")
    assert v.ok and v.avisos


# --- El título de los posts (H1 y tarjetas «En el diario») ---------------------
CUERPO = "Robe dejó Extremoduro en 2019. La gira de 1995 pasó por Bilbao con Platero y Tú."


@pytest.mark.parametrize("h1", [
    "La Evolución Musical de Extremoduro: Un Viaje Inigualable",
    "Robe: De Chapista a Ícono del Rock Español",
    "Robe: Frases Icónicas y su Significado Profundo",
    "Explorando la Frustración en 'Relación Convencional'",
])
def test_los_titulos_de_post_de_molde_caen(h1):
    assert not seo_style.h1_post_verdict(h1, body_md=CUERPO).ok, h1


@pytest.mark.parametrize("h1", [
    "La gira de Extremoduro y Platero y Tú en 1995",
    "Once canciones de Extremoduro que nunca sonaron en directo",
])
def test_los_titulos_de_post_buenos_pasan(h1):
    v = seo_style.h1_post_verdict(h1, body_md=CUERPO)
    assert v.ok, v.motivos


# --- El listener corrige el título de los posts nuevos --------------------------
from app.services.seo_style import titulo_post_a_la_espanola  # noqa: E402

CUERPO_POST = ("Robe grabó con Ara Malikian en Bilbao. Tocaron Los Suaves con El Drogas. "
               "La gira pasó por Plasencia.")


@pytest.mark.parametrize("antes,despues", [
    ("La Evolución Musical de Extremoduro: Un Viaje Inigualable",
     "La evolución musical de Extremoduro: un viaje inigualable"),
    ("Robe: De Chapista a Ícono del Rock Español", "Robe: de chapista a ícono del rock español"),
    ("Explorando la Frustración en 'Relación convencional'",
     "Explorando la frustración en «Relación convencional»"),
    # Un nombre que el cuerpo no menciona se queda: mejor «Beirut» de más que «beirut».
    ("Ara Malikian: Un Viaje Musical Desde Beirut a Extremoduro",
     "Ara Malikian: un viaje musical desde Beirut a Extremoduro"),
    ("El Drogas y Los Suaves en directo", "El Drogas y Los Suaves en directo"),
    ("Qué cuenta «Segundo movimiento: Lo de fuera»", "Qué cuenta «Segundo movimiento: Lo de fuera»"),
])
def test_titulo_de_post_a_la_espanola(antes, despues):
    assert titulo_post_a_la_espanola(antes, CUERPO_POST) == despues


def test_sin_cuerpo_no_se_toca():
    assert titulo_post_a_la_espanola("Un Viaje Inigualable", "") == "Un Viaje Inigualable"
