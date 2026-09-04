"""Tests del re-enlazado retroactivo.

Lo que blindan: que el cron dominical no borre enlaces que luego nadie puede
reponer. `relink_existing` desnudaba TODOS los enlaces del cuerpo y volvía a
enlazar con el índice del corpus, pero ese índice solo contiene
album/artist/band/concept/person/place/song/theme. Un enlace curado a mano a
`/sellos/warner` o a `/libros/de-profundis` se perdía cada domingo y no volvía
jamás. Medido el 03-08-2026 sobre las fichas de disco ya optimizadas.
"""
from __future__ import annotations

from scripts.seo.relink_existing import _desnudar, _path


def test_path_normaliza_absolutas_y_relativas():
    assert _path("https://entreinteriores.com/extremoduro/agila") == "/extremoduro/agila"
    assert _path("/extremoduro/agila/") == "/extremoduro/agila"
    assert _path("/sellos/warner") == "/sellos/warner"


def test_desnuda_lo_que_el_autolinker_sabe_reponer():
    md = "Un disco de [Extremoduro](https://entreinteriores.com/extremoduro) del 96."
    assert _desnudar(md, {"/extremoduro"}) == "Un disco de Extremoduro del 96."


def test_conserva_lo_que_esta_fuera_del_indice():
    """El caso que costaba enlaces: destinos que el corpus no puede regenerar."""
    md = ("Fichó por [Warner](/sellos/warner) y lo cuenta "
          "[De Profundis](/libros/de-profundis).")
    assert _desnudar(md, {"/extremoduro", "/extremoduro/agila"}) == md


def test_mezcla_desnuda_solo_los_del_indice():
    md = ("[Extremoduro](https://entreinteriores.com/extremoduro) fichó por "
          "[Warner](/sellos/warner).")
    assert _desnudar(md, {"/extremoduro"}) == "Extremoduro fichó por [Warner](/sellos/warner)."


def test_no_toca_las_imagenes():
    md = "![Portada de Agila](/album-covers/agila.jpg)"
    assert _desnudar(md, {"/album-covers/agila.jpg"}) == md
