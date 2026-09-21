"""Tests del detector de duplicados que usan el triage y el aviso diario.

Los casos NO son inventados: son títulos reales de la cola de producción, con el
ratio que mide `SequenceMatcher`. El umbral se calibró contra ellos, así que si
alguien lo mueve, estos tests dicen qué deja de verse y qué empieza a chillar.
"""
from __future__ import annotations

from app.db.models import Post
from app.services.triage import UMBRAL_PARECIDO, duplicado_de, normaliza, parecido


def _post(pid: int, titulo: str, kw: str | None = None) -> Post:
    return Post(id=pid, title=titulo, target_keyword_slug=kw)


# --- Normalización ---------------------------------------------------------- #
def test_las_palabras_de_todos_los_titulos_no_cuentan():
    """«Robe» y «Extremoduro» salen en casi todos los títulos del sitio: si
    contaran, todo se parecería a todo."""
    assert "robe" not in normaliza("La evolución de Robe")
    assert "extremoduro" not in normaliza("Extremoduro en directo")


def test_las_tildes_no_separan_dos_titulos_iguales():
    assert parecido("La Evolución Musical", "La Evolucion Musical") == 1.0


# --- Duplicados ------------------------------------------------------------- #
def test_caza_el_duplicado_real_de_produccion():
    """Caso medido el 21-09-2026: la entrada #58 era un calco de la publicada #45."""
    nueva = _post(58, "Extremoduro: La Evolución del Rock Transgresivo en España")
    publicada = _post(45, "Extremoduro: La Evolución del Rock Transgresivo")

    dup = duplicado_de(nueva, [publicada])

    assert dup is not None
    otro, ratio = dup
    assert otro.id == 45
    assert ratio >= UMBRAL_PARECIDO


def test_dos_temas_distintos_no_son_duplicado():
    """El caso que marca el suelo del umbral: 0,53 y son cosas distintas."""
    a = _post(1, "La Hoguera")
    b = _post(2, "Pedrá en directo (1995): media hora de puro directo")

    assert duplicado_de(a, [b]) is None


def test_la_misma_keyword_objetivo_es_duplicado_seguro():
    """Aunque los títulos no se parezcan: compiten por la MISMA búsqueda."""
    a = _post(1, "Un título cualquiera", kw="robe-discografia")
    b = _post(2, "Otro título del todo distinto", kw="robe-discografia")

    dup = duplicado_de(a, [b])

    assert dup is not None and dup[1] == 1.0


def test_un_post_no_se_duplica_a_si_mismo():
    a = _post(7, "El vínculo entre Kutxi Romero y Robe")
    assert duplicado_de(a, [a]) is None


def test_se_queda_con_el_parecido_mas_alto():
    nueva = _post(58, "Extremoduro: La Evolución del Rock Transgresivo en España")
    lejano = _post(10, "Extremoduro: La Evolución del Rock")
    calcado = _post(45, "Extremoduro: La Evolución del Rock Transgresivo")

    dup = duplicado_de(nueva, [lejano, calcado])

    assert dup is not None and dup[0].id == 45
