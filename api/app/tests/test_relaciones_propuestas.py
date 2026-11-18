from scripts.relaciones.propuestas import keyword_de


def test_una_coma_no_tumba_la_tanda():
    # 18-11-2026: «Garden Lodge, Kensington» hizo que DataForSEO rechazara las 193.
    assert keyword_de("Garden Lodge, Kensington") == "garden lodge kensington"


def test_quita_lo_que_dataforseo_no_admite():
    assert keyword_de("Fito & Fitipaldis") == "fito & fitipaldis"
    assert keyword_de("¿Dónde están mis amigos?") == "dónde están mis amigos"
    assert keyword_de("Rock «transgresivo» (1994)") == "rock transgresivo 1994"


def test_lo_que_no_se_puede_medir_se_deja_vacio():
    assert keyword_de("") == ""
    assert keyword_de("palabra " * 11) == ""
    assert keyword_de("x" * 81) == ""
