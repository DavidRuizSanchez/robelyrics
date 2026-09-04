"""La de-repetición no puede destrozar un título.

`derepeat_pages` sustituye menciones repetidas del sujeto por referencias
genéricas («el disco», «esta obra»). El enmascarado solo protege lo
entrecomillado de 12+ caracteres, así que los títulos CORTOS («Pedrá»,
«Prometeo») quedaban desprotegidos y el LLM los sustituía dentro de sus propias
comillas. Se publicó en producción:

    La composición de "esta obra" refleja la habilidad de Robe…
    "Prometeo" en particular, al igual que "la banda", aborda la lucha…

Unas comillas marcan un título: un genérico entrecomillado nunca es correcto.
"""
from scripts.seo.derepeat_pages import _genericos_entrecomillados


def test_detecta_el_generico_disfrazado_de_titulo():
    texto = 'La composición de "esta obra" refleja la habilidad de Robe.'
    assert _genericos_entrecomillados(texto) == ['"esta obra"']


def test_detecta_varios_y_con_comillas_angulares():
    texto = ('"Prometeo" en particular, al igual que "la banda", aborda la lucha; '
             'y «el grupo» insiste en ello.')
    hallados = _genericos_entrecomillados(texto)
    assert len(hallados) == 2
    assert any("la banda" in h for h in hallados)
    assert any("el grupo" in h for h in hallados)


def test_no_marca_el_generico_suelto_que_es_correcto():
    """Sin comillas, «el disco» es exactamente lo que este script busca escribir."""
    texto = ("El disco salió en 1996. La banda lo grabó en Madrid y el álbum "
             "vendió 75.000 copias.")
    assert _genericos_entrecomillados(texto) == []


def test_no_marca_un_titulo_de_verdad_entrecomillado():
    texto = 'En "Extremaydura" y «Jesucristo García», Robe canta a su tierra.'
    assert _genericos_entrecomillados(texto) == []
