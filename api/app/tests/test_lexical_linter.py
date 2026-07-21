"""Tests del linter léxico (anti-muletilla, Eje E del vuelco editorial).

Caso real del feedback de una fan: el verbo "encapsula" aparecía 5-6 veces en un
post y lo hacía pesado. Ningún control determinista lo cazaba.
"""
from __future__ import annotations

from app.services.text_sanitizer import lexical_repetition_report


def test_caza_encapsula_repetido():
    text = (
        "La canción encapsula la rabia. El estribillo encapsula el desamor. "
        "La música encapsula la tensión y la letra encapsula todo el disco. "
        "Aquí Robe encapsula su mundo."
    )
    r = lexical_repetition_report(text)
    assert r.has_problems
    palabras = [w for w, _ in r.overused]
    assert any(w.startswith("encaps") for w in palabras)


def test_familia_lexica_se_agrupa():
    # encapsula / encapsulan / encapsulación cuentan como la misma raíz.
    text = "Encapsula uno. Encapsulan dos. La encapsulación tercera."
    r = lexical_repetition_report(text)
    assert any(w.startswith("encaps") for w, _ in r.overused)


def test_muletillas_de_relleno():
    text = "Es una metáfora poderosa. No es casualidad que cabe destacar el final."
    r = lexical_repetition_report(text)
    assert "metáfora poderosa" in r.burned
    assert "no es casualidad" in r.burned
    assert "cabe destacar" in r.burned


def test_nombres_propios_repiten_sin_penalizar():
    text = " ".join(["Robe"] * 8) + " " + " ".join(["Extremoduro"] * 6)
    r = lexical_repetition_report(text)
    assert not any(w in ("robe", "extremoduro") for w, _ in r.overused)


def test_texto_limpio_no_da_falsos_positivos():
    text = (
        "Deltoya es un disco de 1992. Robe firma unas letras crudas y hermosas, "
        "con imágenes que cambian de sentido según los años que tengas al oírlas."
    )
    r = lexical_repetition_report(text)
    assert not r.has_problems


def test_ignora_urls_y_codigo():
    text = "Mira https://ejemplo.com/encapsula-encapsula y `encapsula()`. Nada más."
    r = lexical_repetition_report(text)
    # "encapsula" solo aparece en URL/código → no debe contar como repetición.
    assert not any(w.startswith("encaps") for w, _ in r.overused)
