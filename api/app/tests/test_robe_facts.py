"""Tests de la fuente única de verdad sobre Robe.

El dato más importante del sitio —que Robe murió— vivía escrito a mano en cuatro
constantes y en seis redacciones de prompt distintas. Con siete copias, ninguna
manda: basta que una se quede vieja para que el sitio se contradiga. Estos tests
vigilan que siga habiendo una sola, y que la discografía no vuelva a escribirse
a mano (si se escribe, un disco nuevo no aparece hasta que alguien se acuerde).
"""
from __future__ import annotations

from datetime import date

from app.services import robe_facts as rf


class _Album:
    def __init__(self, title, year, kind="studio"):
        self.title, self.year, self.kind = title, year, kind


class _DB:
    """Doble mínimo: devuelve las filas (album, artist_slug) que se le den."""

    def __init__(self, filas):
        self._filas = filas

    def execute(self, _stmt):
        filas = self._filas

        class _R:
            def all(self_inner):
                return filas

        return _R()


# --- Una sola fecha --------------------------------------------------------- #
def test_las_cuatro_constantes_viejas_son_la_misma():
    from app.services.content_generator import ROBE_BIRTH_DATE, ROBE_DEATH_DATE
    from app.services.instagram.config import ROBE_DEATH
    from scripts.blog.generate_proposals import ROBE_BIRTH
    from scripts.blog.generate_proposals import ROBE_DEATH as PROP_DEATH
    from scripts.blog.publish_anniversary import BIRTH_DATE, DEATH_DATE

    assert ROBE_DEATH_DATE == ROBE_DEATH == DEATH_DATE == rf.DEATH_DATE
    assert ROBE_BIRTH_DATE == BIRTH_DATE == rf.BIRTH_DATE
    assert (rf.DEATH_DATE.month, rf.DEATH_DATE.day) == PROP_DEATH
    assert (rf.BIRTH_DATE.month, rf.BIRTH_DATE.day) == ROBE_BIRTH


def test_la_fecha_es_la_documentada():
    assert date(2025, 12, 10) == rf.DEATH_DATE
    assert date(2019, 12, 18) == rf.EXTREMODURO_DISSOLUTION_DATE


# --- La causa no se afirma -------------------------------------------------- #
def test_no_existe_una_causa_de_la_muerte_que_publicar():
    """La agencia no dio detalles médicos y nadie los ha confirmado después. El
    tromboembolismo de nov-2024 es un ANTECEDENTE, no la causa."""
    assert rf.DEATH_CAUSE_PUBLIC is None
    assert "no se hizo pública" in rf.DEATH_CAUSE_NOTE
    assert "noviembre de 2024" in rf.DEATH_ANTECEDENT


def test_el_ancla_prohibe_afirmar_la_causa():
    ancla = rf.anchor_prompt()
    assert "no la afirmes ni la insinúes" in ancla
    assert "no se hizo pública" in ancla


# --- La discografía sale de la BD ------------------------------------------- #
def test_la_discografia_sale_del_catalogo_no_de_una_lista_escrita_a_mano():
    """Si se hardcodease, un disco nuevo no aparecería hasta que alguien lo
    añadiera a mano. Con un disco inventado en el doble, tiene que salir."""
    db = _DB([(_Album("Un disco que no existe", 2031), "robe")])

    discos = rf.discography(db)

    assert [d.title for d in discos] == ["Un disco que no existe"]
    assert rf.latest_release(db).year == 2031


def test_sin_catalogo_no_se_inventa_nada():
    class _Roto:
        def execute(self, _s):
            raise RuntimeError("BD caída")

    assert rf.discography(_Roto()) == []
    assert rf.latest_release(_Roto()) is None


def test_los_hechos_obligatorios_citan_el_ultimo_disco():
    db = _DB([(_Album("Se nos lleva el aire", 2023), "robe")])

    lineas = " ".join(rf.must_facts_lines(db))

    assert "Se nos lleva el aire" in lineas
    assert "falleció el 10 de diciembre de 2025" in lineas
    assert "18 de diciembre de 2019" in lineas


# --- El debut ---------------------------------------------------------------- #
def test_el_debut_no_es_rock_transgresivo():
    """Dos posts publicados afirmaban que el debut fue «Rock Transgresivo»
    (1994). El debut es «Tú en tu casa…» (1990); el otro es la regrabación."""
    assert rf.EXTREMODURO_DEBUT == ("Tú en tu casa, nosotros en la hoguera", 1990)
    assert "Rock Transgresivo" in rf.anchor_prompt()
    assert "no el debut" in rf.anchor_prompt()
