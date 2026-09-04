"""Tests del recorte de biografías.

Lo que blindan: que cortar un texto no cambie lo que el texto dice. Un
`extract[:500]` a pelo dejó la bio de Uoho en «…la banda Inconscientes, su etapa
como vocalista principa», cuando la frase entera era «…su etapa como vocalista
principal EN SU BREVE PROYECTO SOLISTA UOHO». El recorte convirtió un dato
correcto en uno falso —daba a entender que cantaba en Inconscientes, cuando el
vocalista era Jon Calvo— y así salió publicado en Instagram el 03-08-2026, donde
un seguidor tuvo que corregirlo en los comentarios.
"""
from __future__ import annotations

from scripts.seed_persons import _recorta_por_frase


def test_lo_que_cabe_no_se_toca():
    t = "Una biografía corta que cabe entera."
    assert _recorta_por_frase(t, 500) == t


def test_corta_en_el_final_de_frase_no_a_mitad_de_palabra():
    t = ("Iñaki Antón es guitarrista de Extremoduro. Otros proyectos suyos son "
         "la banda Inconscientes, su etapa como vocalista principal en su "
         "proyecto solista UOHO y su última banda Rebrote.")

    r = _recorta_por_frase(t, 60)

    assert r == "Iñaki Antón es guitarrista de Extremoduro."
    assert not r.endswith("principa")


def test_el_caso_real_de_uoho_no_se_queda_a_medias():
    """Si no cabe la frase del proyecto solista, tampoco se insinúa."""
    t = ("Otros proyectos notables en los que Iñaki se ha involucrado fue la "
         "banda Inconscientes, su etapa como vocalista principal en su breve "
         "proyecto solista UOHO y su última banda Rebrote.")

    r = _recorta_por_frase(t, 130)

    # Nada de cortar dejando «vocalista principa» colgando.
    assert "vocalista principa" not in r or "vocalista principal en" in r
    assert r.endswith("…") or r.endswith(".")


def test_sin_final_de_frase_corta_por_palabra_y_avisa():
    t = "palabra " * 200

    r = _recorta_por_frase(t, 50)

    assert r.endswith("…")
    assert not r.replace("…", "").endswith("pala")


def test_normaliza_los_espacios():
    assert _recorta_por_frase("  hola   mundo  ", 500) == "hola mundo"


def test_vacio_no_revienta():
    assert _recorta_por_frase("", 500) == ""
    assert _recorta_por_frase(None, 500) == ""
