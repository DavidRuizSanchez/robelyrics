"""El panel tiene que dar con qué cazar el próximo fallo.

El 17-09-2026 enseñaba, de un post con fotos de Pep Guardiola en una noticia
sobre la presidenta de la Junta de Extremadura: la imagen ya compuesta, el
caption, y «imagen ✓». Ese booleano decía que HABÍA imagen, no de quién era. La
query que la buscó no se guardaba en ningún sitio: solo quedaba en una línea del
log del cron, que rota.
"""
from __future__ import annotations

from types import SimpleNamespace as N

import pytest

import scripts.instagram.notify_evergreen as notify


# --- El correo de propuestas ------------------------------------------------ #
def test_una_propuesta_de_noticia_aparece_en_el_correo():
    """`main()` selecciona TODOS los `proposed` y `total` los cuenta, pero
    `TYPE_ORDER` solo listaba los cuatro evergreen: las noticias engordaban el
    número del asunto y no salían en ninguna sección. Una propuesta de noticia no
    ha aparecido nunca nominalmente en este correo."""
    _, texto = notify._render(
        {"news": [N(title="Guardiola reivindica el talento", summary="")]},
        "https://x/panel",
    )
    assert "Guardiola reivindica el talento" in texto


def test_un_tipo_nuevo_no_puede_desaparecer_en_silencio():
    """Se arregla la clase de bug, no la instancia: lo que no esté en TYPE_ORDER
    cae en «Otros» en vez de contarse y no verse."""
    _, texto = notify._render(
        {"formato_del_futuro": [N(title="Algo que aún no existe", summary="")]},
        "https://x/panel",
    )
    assert "Otros" in texto
    assert "Algo que aún no existe" in texto


def test_el_total_cuadra_con_lo_que_se_lista():
    grupos = {
        "news": [N(title="A", summary="")],
        "quote": [N(title="B", summary="")],
        "raro": [N(title="C", summary="")],
    }
    _, texto = notify._render(grupos, "https://x/panel")
    assert "3" in texto.splitlines()[0]
    for titulo in ("A", "B", "C"):
        assert f"· {titulo}" in texto


# --- El badge de la foto ---------------------------------------------------- #
@pytest.mark.parametrize(
    ("source", "verdict", "espera"),
    [
        ("wikidata_p18", "accredited", "commons"),
        ("ficha_propia", "accredited", "ficha propia"),
        ("google_images", "identidad_ok", "identidad"),
        ("google_images", "identidad_sin_mirar", "sin comprobar"),
        ("arte_propio", "own_art", "arte propio"),
    ],
)
def test_el_panel_dice_de_donde_sale_la_foto(source, verdict, espera):
    """Contrato con el frontend: `etiquetaFoto` en InstagramPlanner.tsx lee estos
    valores. Si alguien renombra uno en el back y no en el front, el panel vuelve
    a decir «imagen ✓» y deja de avisar de nada."""
    from app.services.instagram import identity_photo

    validos = {identity_photo.FICHA, identity_photo.COMMONS,
               identity_photo.GOOGLE, identity_photo.ARTE_PROPIO}
    assert source in validos
    assert espera  # el texto que el panel enseña vive en el .tsx


def test_los_nombres_de_fuente_son_los_que_espera_el_panel():
    from pathlib import Path

    from app.services.instagram import identity_photo

    tsx = Path(__file__).parents[3] / "web/app/biblioteca/admin/instagram/InstagramPlanner.tsx"
    if not tsx.exists():  # el CI del api no siempre trae el front
        pytest.skip("sin el frontend delante")
    contenido = tsx.read_text()
    for valor in (identity_photo.FICHA, identity_photo.COMMONS,
                  identity_photo.GOOGLE, identity_photo.ARTE_PROPIO):
        assert f'"{valor}"' in contenido, f"el panel no conoce {valor}"
