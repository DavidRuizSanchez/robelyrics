"""Un texto que confiesa no saber no informa (10-11-2026).

Las frases son literales de los borradores que el motor escribió ese día para
las fichas de Ángel Lorenzo y María Timón y para la idea #527 del blog.
"""
from app.services import robe_facts, source_guard


def test_quita_las_confesiones_reales_y_deja_lo_demas():
    texto = (
        "## Ángel Lorenzo, el primer batería\n\n"
        "Ángel Lorenzo fue batería de Extremoduro en 1987. No hay datos que documenten "
        "grabaciones ni conciertos suyos con la banda.\n\n"
        "## El festival\n\n"
        "El festival se celebró el 16 de mayo de 2026. El material no detalla el programa "
        "ni indica si el festival tendrá periodicidad."
    )
    limpio, quitadas = source_guard.quitar_confesiones(texto)
    assert "fue batería de Extremoduro en 1987." in limpio
    assert "se celebró el 16 de mayo de 2026." in limpio
    assert "No hay datos" not in limpio and "no detalla" not in limpio
    assert len(quitadas) == 2


def test_una_seccion_que_solo_confiesa_desaparece_con_su_heading():
    texto = (
        "## Quién es\n\nMaría Timón cantó coros en «Somos unos animales».\n\n"
        "## Qué hace actualmente María Timón\n\n"
        "No hay información para establecer qué hace hoy. Los resultados de búsqueda "
        "mencionan a otras personas llamadas María.\n\n"
        "## Deltoya\n\nPuso voces en «Papel secante»."
    )
    limpio, quitadas = source_guard.quitar_confesiones(texto)
    assert "Qué hace actualmente" not in limpio
    assert "## Quién es" in limpio and "## Deltoya" in limpio
    assert "## Qué hace actualmente María Timón" in quitadas


def test_un_verso_entre_comillas_no_es_una_confesion():
    texto = "Robe canta «no se sabe muy bien por qué» en esa canción."
    limpio, quitadas = source_guard.quitar_confesiones(texto)
    assert limpio == texto and quitadas == []


def test_sin_confesiones_no_toca_nada_ni_los_headings_vacios_previos():
    texto = "## A\n\n## B\n\nDato concreto de 1983."
    assert source_guard.quitar_confesiones(texto) == (texto, [])


def test_el_ancla_de_robe_no_obliga_fuera_de_su_trayectoria():
    """Pedía contar su muerte en TODO texto: salía en la ficha de Paco Doniga."""
    ancla = robe_facts.anchor_prompt()
    assert "DEBE decirlo" in ancla          # en su trayectoria sigue obligando
    assert "ALCANCE" in ancla and "otra persona" in ancla


def test_augment_usa_la_misma_lista():
    from scripts.seo import augment_deep

    assert augment_deep._CONFESIONES is source_guard.CONFESIONES
    assert augment_deep.confiesa_no_saber("Se desconoce la fecha.") == "se desconoce"


def test_la_vara_de_las_personas_no_pide_discografia_a_todos():
    """Criterio de David (10-11-2026): a un muralista no se le piden discos y una
    ficha breve vale si todo es concreto. El resto de tipos sigue con 250."""
    from app.services import editorial_review as er

    assert er._min_words("person") == 150
    assert er._min_words("blog") == er.MIN_WORDS == 250
    rubrica = er._rubric_for("person")
    assert "obras si es artista" in rubrica and "ficha breve" in rubrica
