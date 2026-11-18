"""Tests del re-enlazado retroactivo.

Lo que blindan: que el cron dominical no borre enlaces que luego nadie puede
reponer. Hasta el 03-08-2026 desnudaba TODOS los enlaces y un `/sellos/warner`
curado a mano se perdía cada domingo. Desde el 11-11-2026 no desnuda nada:
valida y completa (ver `test_link_policy.py` para el punto fijo).
"""
from __future__ import annotations

from scripts.seo.relink_existing import _clean, _path

INDICE = [
    {"name": "Extremoduro", "norm": "extremoduro",
     "url": "https://entreinteriores.com/extremoduro", "type": "artist"},
    {"name": "Agila", "norm": "agila",
     "url": "https://entreinteriores.com/extremoduro/agila", "type": "album"},
]


def test_path_normaliza_absolutas_y_relativas():
    assert _path("https://entreinteriores.com/extremoduro/agila") == "/extremoduro/agila"
    assert _path("/extremoduro/agila/") == "/extremoduro/agila"
    assert _path("/sellos/warner") == "/sellos/warner"


def test_conserva_lo_que_esta_fuera_del_indice():
    """El caso que costaba enlaces: destinos que el corpus no puede regenerar."""
    md = ("Fichó por [Warner](/sellos/warner) y lo cuenta "
          "[De Profundis](/libros/de-profundis).")
    assert _clean(md, INDICE, {}) == md


def test_no_quita_un_enlace_del_indice_que_ya_estaba():
    """Antes se desnudaba y se volvía a elegir: un enlace con anchor que no es
    variante exacta del índice («los de Plasencia») no volvía."""
    md = "Un disco de [los de Plasencia](https://entreinteriores.com/extremoduro) del 96."
    assert _clean(md, INDICE, {}) == md


def test_completa_hasta_el_tope_sin_tocar_lo_que_hay():
    md = "[Warner](/sellos/warner) editó Agila, de Extremoduro."
    out = _clean(md, INDICE, {})
    assert out.startswith("[Warner](/sellos/warner)")
    assert "[Agila](https://entreinteriores.com/extremoduro/agila)" in out
    assert "[Extremoduro](https://entreinteriores.com/extremoduro)" in out


def test_no_toca_las_imagenes():
    md = "![Portada de Agila](/album-covers/agila.jpg)"
    assert _clean(md, INDICE, {}) == md
