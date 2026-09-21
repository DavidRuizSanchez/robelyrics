"""Tests del filtro que decide qué hechos verificados alcanzan al motor.

El fallo que blindan se midió el 21-09-2026: el filtro descartaba toda clave de
menos de cinco caracteres y «Robe» tiene cuatro, así que el sujeto central del
sitio se buscaba SOLO por «Roberto Iniesta» —que casi nunca se escribe así—.
Resultado: de 268 líneas de `data/reference/*.md`, la entidad Robe alcanzaba 3, y
la del fallecimiento no la alcanzaba nadie. Por eso se publicó un recorrido por
toda la trayectoria de Extremoduro que terminaba en 2021.

Al arreglarlo hay que evitar el extremo contrario: buscar «robe» como subcadena
casa «probé», «robé» y «Roberto», y llenaría las fichas de ruido.
"""
from __future__ import annotations

import pathlib

from app.services import deep_research as dr


def _referencias(tmp_path: pathlib.Path, contenido: str) -> pathlib.Path:
    """Directorio de referencias de mentira, con una sola línea dentro."""
    ref = tmp_path / "reference"
    ref.mkdir()
    (ref / "hechos.md").write_text(contenido, encoding="utf-8")
    return ref


def test_una_clave_corta_alcanza_su_linea(tmp_path):
    """«Robe» tiene cuatro letras y antes se descartaba entera."""
    ref = _referencias(
        tmp_path,
        "- Robe falleció el 10 de diciembre de 2025, a los 63 años, en la madrugada.\n",
    )

    lineas = dr._reference_facts(["Roberto Iniesta", "Robe"], ref_dir=ref)

    assert any("falleció el 10 de diciembre" in ln for ln in lineas)


def test_una_clave_corta_no_casa_dentro_de_otra_palabra(tmp_path):
    """El riesgo del arreglo: «probé», «robé» y «Roberto» contienen «robe»."""
    ref = _referencias(
        tmp_path,
        "- Yo probé aquel vino y me robé una copa en casa de Roberto Carlos, qué tiempos.\n",
    )

    assert dr._reference_facts(["Robe"], ref_dir=ref) == []


def test_las_claves_largas_siguen_sin_distinguir_acentos(tmp_path):
    ref = _referencias(
        tmp_path,
        "- Mayeutica fue número uno en PROMUSICAE y lo produjo Álvaro Rodríguez Barroso.\n",
    )

    assert len(dr._reference_facts(["Mayéutica"], ref_dir=ref)) == 1
