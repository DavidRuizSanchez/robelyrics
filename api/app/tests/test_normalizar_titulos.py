"""Títulos de canción con mayúsculas a la española (David, 12-11-2026)."""
from __future__ import annotations

import yaml

from scripts.normalizar_titulos import _CANDIDATOS, reemplazar_titulo

# En CI el repo vive en /app y data/ va montado en /app/data: misma búsqueda que el script.
YAML = next(p for p in _CANDIDATOS if p.exists())


def test_distintivo_se_cambia_en_cualquier_sitio():
    t = "Letra de «Ábreme el Pecho y Registra», de Extremoduro. Ábreme el Pecho y Registra abre Agila."
    assert reemplazar_titulo(t, "Ábreme el Pecho y Registra", "Ábreme el pecho y registra") == (
        "Letra de «Ábreme el pecho y registra», de Extremoduro. Ábreme el pecho y registra abre Agila.")


def test_corto_solo_citado_o_en_enlace():
    t = "«La Carrera» y [La Carrera](/extremoduro/agila/la-carrera). La Carrera de fondo."
    assert reemplazar_titulo(t, "La Carrera", "La carrera") == (
        "«La carrera» y [La carrera](/extremoduro/agila/la-carrera). La Carrera de fondo.")


def test_el_nombre_de_la_web_no_se_toca_salvo_citado():
    t = "Entre Interiores publica «Entre Interiores», de Extremoduro."
    assert reemplazar_titulo(t, "Entre Interiores", "Entre interiores") == (
        "Entre Interiores publica «Entre interiores», de Extremoduro.")


def test_un_campo_que_es_el_titulo():
    assert reemplazar_titulo("Tu Corazón", "Tu Corazón", "Tu corazón") == "Tu corazón"


def test_no_cambia_dentro_de_otra_palabra():
    t = "Sin Dios Ni Amor"
    assert reemplazar_titulo(t, "Sin Dios Ni Amo", "Sin Dios ni amo") == t


def test_el_yaml_solo_cambia_mayusculas_y_comillas():
    """Ninguna entrada cambia de palabras: solo mayúsculas (y las comillas rotas de
    «Estado policial»). Así ninguna URL ni búsqueda puede moverse."""
    datos = yaml.safe_load(YAML.read_text())
    entradas = datos["canciones"] + datos["discos"]
    assert len(datos["canciones"]) >= 70
    for e in entradas:
        a = e["antes"].lower().replace("”", "").replace("«", "").replace("»", "")
        b = e["titulo"].lower().replace("”", "").replace("«", "").replace("»", "")
        assert a == b, e
        primera = next(c for c in e["titulo"] if c.isalpha())
        assert primera.isupper(), e
