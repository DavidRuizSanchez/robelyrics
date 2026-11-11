"""Enlazado interno: rutas normalizadas y punto fijo (11-11-2026).

`/personas/alen-ayerdi` llegó a enlazar 6 veces a El Dromedario Records con el
mismo anchor. No lo escribió el modelo: el índice del corpus ponía los sellos en
`/grupos/`, el guard los reescribía a `/sellos/` relativo y el autolinker
comparaba las URLs en crudo, así que no veía el enlace que ya había y enlazaba
la siguiente mención. Un enlace más por pasada del cron.

El fixture es el cuerpo publicado en prod el 11-11-2026, con sus 6 enlaces.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.db.models import Band
from app.services.entity_resolver import autolink_corpus, build_corpus_index
from app.services.link_policy import norm_path
from app.services.url_resolver import _reenlazar
from app.tests.test_person_visibility import db  # noqa: F401 — fixture SQLite
from scripts.seo.relink_existing import _clean

BASE = "https://entreinteriores.com"
ALEN = (Path(__file__).parent / "fixtures" / "alen_ayerdi_body.md").read_text()
DROMEDARIO = "/sellos/el-dromedario-records"

_ENLACE = re.compile(r"(?<!\!)\[([^\]]+)\]\(([^)\s]+)\)")


def _destinos(md: str) -> list[str]:
    return [norm_path(u) or u for _, u in _ENLACE.findall(md)]


def _ent(name: str, path: str, type_: str) -> dict:
    return {"name": name, "norm": name.lower(), "url": BASE + path, "type": type_}


INDICE_ALEN = [
    _ent("Marea", "/grupos/marea", "band"),
    _ent("Extremoduro", "/extremoduro", "artist"),
    _ent("El Dromedario Records", DROMEDARIO, "band"),
    _ent("Lo que aletea en nuestras cabezas",
         "/robe/lo-que-aletea-en-nuestras-cabezas", "album"),
    _ent("Mayéutica", "/robe/mayeutica", "album"),
    _ent("Ciclonautas", "/grupos/ciclonautas", "band"),
    _ent("Pamplona", "/lugares/pamplona", "place"),
]


# --------------------------------------------------------------------------- #
# norm_path
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("url,esperado", [
    ("https://entreinteriores.com/sellos/x", "/sellos/x"),
    ("https://www.entreinteriores.com/sellos/x/", "/sellos/x"),
    ("/sellos/x", "/sellos/x"),
    ("/sellos/x/", "/sellos/x"),
    ("/sellos/x#historia", "/sellos/x"),
    ("/sellos/x?utm=1", "/sellos/x"),
    ("https://entreinteriores.com", "/"),
    ("/", "/"),
])
def test_norm_path_internas(url, esperado):
    assert norm_path(url) == esperado


@pytest.mark.parametrize("url", [
    "https://es.wikipedia.org/wiki/Extremoduro",
    "https://entreinteriores.com.evil.example/sellos/x",
    "mailto:hola@example.com",
    "#notas",
    "",
    None,
    "relativa/sin/barra",
])
def test_norm_path_externas_o_no_navegables(url):
    assert norm_path(url) is None


# --------------------------------------------------------------------------- #
# Relativa contra absoluta: la causa raíz
# --------------------------------------------------------------------------- #
def test_un_enlace_relativo_cuenta_como_el_absoluto_del_indice():
    md = "Fundó [El Dromedario Records](/sellos/el-dromedario-records). Luego El Dromedario Records creció."
    indice = [_ent("El Dromedario Records", DROMEDARIO, "band")]
    assert autolink_corpus(md, indice, max_links=4) == md


def test_barra_final_y_fragmento_no_cuentan_como_otro_destino():
    md = "Ver [Extremoduro](/extremoduro/#historia). Extremoduro grabó Agila."
    indice = [_ent("Extremoduro", "/extremoduro", "artist")]
    assert autolink_corpus(md, indice, max_links=4) == md


def test_el_relativo_consume_tope():
    """Un enlace ya presente al corpus, relativo, gasta presupuesto."""
    md = "[Marea](/grupos/marea) y Extremoduro."
    indice = [_ent("Marea", "/grupos/marea", "band"),
              _ent("Extremoduro", "/extremoduro", "artist")]
    assert autolink_corpus(md, indice, max_links=1) == md


# --------------------------------------------------------------------------- #
# Índice: los sellos van a /sellos/
# --------------------------------------------------------------------------- #
def test_los_sellos_se_indexan_en_sellos_y_los_grupos_en_grupos(db):  # noqa: F811
    db.add_all([
        Band(slug="el-dromedario-records", name="El Dromedario Records", kind="label"),
        Band(slug="marea", name="Marea", kind="band"),
    ])
    db.flush()
    urls = {e["name"]: e["url"] for e in build_corpus_index(db)}
    assert urls["El Dromedario Records"] == BASE + DROMEDARIO
    assert urls["Marea"] == BASE + "/grupos/marea"


# --------------------------------------------------------------------------- #
# Punto fijo: el ciclo real del cron no acumula
# --------------------------------------------------------------------------- #
def _guard_relativiza(md: str) -> str:
    """Peor caso del guard / `audit_urls --fix`: reescribe a relativa toda ruta
    interna absoluta (lo que hace `_reenlazar` con las que redirigen)."""
    for url in {u for _, u in _ENLACE.findall(md) if u.startswith(BASE)}:
        md = _reenlazar(md, norm_path(url), norm_path(url))
    return md


def _semana(md: str, n: int) -> str:
    # `link_stats` cambia cada semana: el resultado no puede depender de ello.
    stats = {norm_path(e["url"]): (n * 7 + i) % 5 for i, e in enumerate(INDICE_ALEN)}
    md = _clean(md, INDICE_ALEN, stats, exclude_slug="alen-ayerdi")
    return _guard_relativiza(md)


def test_alen_ayerdi_no_suma_un_enlace_por_pasada():
    antes = _destinos(ALEN).count(DROMEDARIO)
    assert antes == 6  # el estado real de prod el 11-11-2026
    md = ALEN
    for n in range(6):
        md = _semana(md, n)
    # Nunca crece. Quitar los 5 sobrantes es la limpieza (otro PR), no el cron.
    assert _destinos(md).count(DROMEDARIO) == antes
    # Ya tiene sus 4 destinos del corpus: el cron no tiene nada que añadir.
    assert md == _guard_relativiza(ALEN)


def test_ciclo_completo_es_punto_fijo_desde_la_segunda_pasada():
    sin_enlaces = _ENLACE.sub(r"\1", ALEN)
    primera = _semana(sin_enlaces, 0)
    assert _destinos(primera), "la primera pasada tiene que enlazar algo"
    md = primera
    for n in range(1, 6):
        md = _semana(md, n)
        assert md == primera, f"la pasada {n + 1} cambió el cuerpo"


def test_primera_pasada_enlaza_cada_destino_una_sola_vez():
    sin_enlaces = _ENLACE.sub(r"\1", ALEN)
    destinos = _destinos(_semana(sin_enlaces, 0))
    assert len(destinos) == len(set(destinos))
    assert len(destinos) <= 4


def test_relink_no_pierde_ningun_enlace_del_cuerpo_real():
    md = _semana(ALEN, 0)
    assert _ENLACE.sub(r"\1", md) == _ENLACE.sub(r"\1", ALEN)  # mismo texto
    assert sorted(_destinos(md)) == sorted(_destinos(_guard_relativiza(ALEN)))
