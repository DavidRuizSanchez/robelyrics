"""El gate de no-pérdida tiene que rechazar lo que se deja algo por el camino.

Cada test es un caso real de los que se midieron el 02-08-2026 sobre las 173
fichas publicadas: 1.925 versos citados, 686 enlaces internos, 325 años.
"""
from app.services.content_guard import (
    anclaje_factual,
    extract_facts,
    extract_topics,
    find_especulacion,
    no_loss_verdict,
    topic_coverage,
)

ORIGINAL = """## El contexto de Agila

«Agila» salió en 1996 y lo grabaron en los [Estudios Box](/lugares/estudios-box).

## Las canciones

Robe escribió «Yo soy el que soy» pensando en otra cosa.
Ver también [Deltoya](/extremoduro/deltoya).

## El legado

Vendió 75000 copias.
"""


def test_extrae_los_hechos_que_hay_que_conservar():
    f = extract_facts(ORIGINAL)
    # «Agila» (5 chars) NO cuenta como verso: el suelo de 12 caracteres está
    # para no confundir un título entrecomillado con una cita de la letra.
    assert f.verses == frozenset({"yo soy el que soy"})
    assert "/extremoduro/deltoya" in f.links
    assert "1996" in f.years
    assert extract_topics(ORIGINAL) == [
        "El contexto de Agila", "Las canciones", "El legado",
    ]


def test_rechaza_si_pierde_un_verso():
    nuevo = ORIGINAL.replace("Robe escribió «Yo soy el que soy» pensando en otra cosa.",
                             "Robe escribió la canción pensando en otra cosa.")
    v = no_loss_verdict(ORIGINAL, nuevo)
    assert not v.ok
    assert v.lost_verses == 1
    assert "verso" in v.reason


def test_un_enlace_suelto_no_bloquea_pero_se_contabiliza():
    """El enlazado lo reparte `autolink_corpus` con tope global de 4 y lo
    recalcula `relink_existing` cada domingo: exigir un enlace concreto
    contradiría a ese subsistema. Se cuenta, no se bloquea."""
    nuevo = ORIGINAL.replace("[Deltoya](/extremoduro/deltoya)", "Deltoya")
    v = no_loss_verdict(ORIGINAL, nuevo)
    assert v.lost_links == 1
    assert v.ok, v.reason


def test_rechaza_si_pierde_mas_de_la_mitad_de_los_enlaces():
    """Con pocos enlaces la proporción es ruido, así que el suelo son 4 útiles."""
    rico = ORIGINAL + (
        "\n[Pedrá](/extremoduro/pedra) y [Robe](/personas/robe-iniesta) "
        "y [Uoho](/personas/inaki-uoho-anton).\n"
    )
    pobre = (rico
             .replace("[Deltoya](/extremoduro/deltoya)", "Deltoya")
             .replace("[Estudios Box](/lugares/estudios-box)", "Estudios Box")
             .replace("[Pedrá](/extremoduro/pedra)", "Pedrá"))
    v = no_loss_verdict(rico, pobre)
    assert not v.ok
    assert "enlaces internos" in v.reason


def test_enlace_exento_no_cuenta_como_perdida():
    nuevo = ORIGINAL.replace("[Deltoya](/extremoduro/deltoya)", "Deltoya")
    v = no_loss_verdict(ORIGINAL, nuevo, exempt_links={"/extremoduro/deltoya"})
    assert v.ok, v.reason
    assert v.lost_links == 0


def test_rechaza_si_pierde_un_ano():
    nuevo = ORIGINAL.replace("salió en 1996", "salió a mediados de los noventa")
    v = no_loss_verdict(ORIGINAL, nuevo)
    assert not v.ok
    assert v.lost_years == 1


def test_rechaza_si_se_cae_una_seccion_entera():
    """El caso que motivó el gate: la regeneración se deja un tema fuera."""
    nuevo = ORIGINAL.split("## El legado")[0] + "\n"
    v = no_loss_verdict(ORIGINAL, nuevo)
    assert not v.ok
    # Cae por longitud o por topics; ambas son pérdida real.
    assert v.lost_topics or "encoge" in v.reason


def test_rechaza_si_introduce_especulacion():
    nuevo = ORIGINAL + "\n## Reflexión\n\nLa portada puede interpretarse como una metáfora.\n"
    v = no_loss_verdict(ORIGINAL, nuevo)
    assert not v.ok
    assert v.especulacion


def test_no_penaliza_la_especulacion_que_ya_estaba():
    """Si el original ya especulaba, no es la regeneración quien lo mete."""
    viejo = ORIGINAL + "\n## Nota\n\nQuizás por eso funcionó.\n"
    nuevo = viejo + "\nUn dato más, de 1997, sin adornos.\n"
    v = no_loss_verdict(viejo, nuevo)
    assert v.ok, v.reason


def test_acepta_una_ampliacion_limpia():
    nuevo = ORIGINAL + "\n## La portada\n\nLa dibujó Ramone en 1996.\n"
    v = no_loss_verdict(ORIGINAL, nuevo)
    assert v.ok, v.reason
    assert v.ratio > 1


def test_topic_renombrado_no_cuenta_como_perdido():
    """Reescribir un heading no es perder el tema. Sin API key degrada a léxico,
    que es más estricto: se acepta cualquiera de los dos comportamientos."""
    nuevo = ORIGINAL.replace("## El legado", "## El legado de Agila en el rock")
    faltan = topic_coverage(ORIGINAL, nuevo)
    assert "El legado" not in faltan or len(faltan) <= 1


def test_detecta_relleno_ademas_de_especulacion():
    assert find_especulacion("Marcó un antes y un después en su carrera.")
    assert find_especulacion("Podría verse como un homenaje.")
    assert not find_especulacion("Se grabó en los Estudios Box en 1996.")


def test_anclaje_factual_distingue_dato_de_adorno():
    material = "La portada de Agila la dibujó Ramone, alias Capitán Kavernícola, en 1996."
    assert anclaje_factual("La portada la firmó Ramone, el Capitán Kavernícola.", material)
    assert not anclaje_factual(
        "La portada puede interpretarse como una metáfora de la libertad.", material
    )


def test_el_ano_de_una_cita_no_es_un_dato_del_sujeto():
    """«[Fuente: Mondo Sonoro 2021]» es la fecha de la cita, no del disco.
    Contarla hacía que el gate rechazara regeneraciones por perder un año que
    nunca fue un hecho sobre el sujeto."""
    con_cita = ORIGINAL + "\nAlgo más [Fuente: Mondo Sonoro 2021].\n"
    sin_cita = ORIGINAL + "\nAlgo más, contado de otra manera.\n"
    assert "2021" not in extract_facts(con_cita).years
    v = no_loss_verdict(con_cita, sin_cita)
    assert v.ok, v.reason


def test_los_headings_de_navegacion_no_son_temas():
    """«Otros discos relacionados» lo pone la plantilla, no dice nada del sujeto,
    y su ausencia bloqueaba regeneraciones buenas."""
    md = ORIGINAL + "\n## Otros discos relacionados\n\nVer más.\n## En el diario\n\nPosts.\n"
    temas = extract_topics(md)
    assert "Otros discos relacionados" not in temas
    assert "En el diario" not in temas
    assert "El legado" in temas


def test_la_comparacion_semantica_no_revienta_con_numpy():
    """`array or 1` lanzaba «truth value is ambiguous» y tiraba en silencio la
    comparación a la rama léxica."""
    from app.services.content_guard import _cosine_matrix
    m = _cosine_matrix([[1.0, 0.0], [0.0, 1.0]], [[1.0, 0.0]])
    assert abs(m[0][0] - 1.0) < 1e-5
    assert abs(m[1][0]) < 1e-5


def test_una_cita_que_sigue_en_el_texto_sin_comillas_no_es_perdida():
    """Muchas «citas» son títulos de canción entrecomillados. Si el texto nuevo
    los nombra sin comillas, el contenido sigue ahí."""
    viejo = ORIGINAL
    nuevo = ORIGINAL.replace(
        "Robe escribió «Yo soy el que soy» pensando en otra cosa.",
        "Robe escribió Yo soy el que soy pensando en otra cosa.",
    )
    v = no_loss_verdict(viejo, nuevo)
    assert v.lost_verses == 0
    assert v.ok, v.reason


def test_una_cita_de_prensa_vetada_se_puede_retirar_a_proposito():
    """El extractor no distingue un verso de Robe de una frase de un medio.

    Sin exención, una ficha que cita a Mondo Sonoro —prensa vetada del
    proyecto— no se podía limpiar: el gate exigía conservar justo lo que hay
    que quitar. Caso real: la ficha de «Destrozares» lo citaba tres veces.
    """
    viejo = ('Según Mondo Sonoro, "la música de una pequeña orquesta liga '
             'perfectamente con la voz de Robe". El disco salió en 2016.')
    nuevo = ("El disco salió en 2016 y lo firma una formación nueva, con violín, "
             "clarinete y piano, que es la que explica cómo suena el conjunto.")

    bloquea = no_loss_verdict(viejo, nuevo)
    assert not bloquea.ok
    assert "verso" in (bloquea.reason or "")

    pasa = no_loss_verdict(viejo, nuevo, exempt_verses={
        "la música de una pequeña orquesta liga perfectamente con la voz de Robe"
    })
    assert pasa.ok, pasa.reason


def test_la_exencion_de_citas_no_abre_la_mano_con_las_demas():
    """Eximir una cita concreta no puede dejar pasar la pérdida de otra."""
    viejo = ('Dice "primera cita larga que hay que conservar entera" y también '
             '"segunda cita larga que también hay que conservar".')
    nuevo = "Un texto nuevo que no conserva ninguna de las dos."

    v = no_loss_verdict(viejo, nuevo, exempt_verses={
        "primera cita larga que hay que conservar entera"
    })

    assert not v.ok
    assert v.lost_verses == 1
