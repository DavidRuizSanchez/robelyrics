"""Tests del filtro de relevancia de canales de YouTube.

Los casos NO son inventados: son títulos y descripciones reales de @tesonica,
canal que sube análisis de La Ley Innata mezclados con metal, ergonomía del
violonchelo y vídeos personales. Lo que se blinda aquí es que entre el material
del universo Robe y NO entre el resto — un falso positivo mete en el corpus un
análisis de System of a Down como si hablara de Extremoduro.
"""
from __future__ import annotations

import pytest

from app.services.youtube_relevance import (
    MIN_DISTINCTIVE,
    RelevanceVocab,
    build_vocab,
    is_relevant,
)


@pytest.fixture()
def vocab() -> RelevanceVocab:
    """Vocabulario con títulos reales del catálogo, repartidos como en producción."""
    v = RelevanceVocab()
    for t in (
        "La ley innata",
        "Dulce Introducción al Caos",
        "Primer Movimiento: El Sueño",
        "Cuarto Movimiento: La Realidad",
        "Coda Flamenca (Otra Realidad)",
        "Calle Esperanza S/N",
        "Tercer Movimiento: Lo de Dentro",
    ):
        v.distinctive[_n(t)] = t
    for t in ("La Carrera", "Mama", "Golfa", "Deltoya", "Agila"):
        v.short[_n(t)] = t
    return v


def _n(s: str) -> str:
    from app.services.fact_check import _norm

    return _norm(s)


# --------------------------------------------------------------------------- #
# Lo que SÍ debe entrar
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "title",
    [
        "LA LEY INNATA Capítulo 12 | Coda flamenca (Otra realidad) || Vistazo general 2/2",
        "LA LEY INNATA - Análisis exhaustivo || Primer movimiento: el sueño (2/2)",
        "LA LEY INNATA (ANÁLISIS) | Capítulo 1: contexto",
        "La mayor OBRA DE ARTE de EXTREMODURO | Calle Esperanza S/N",
        "Dulce Introducción al Caos || ANÁLISIS FINAL: estructura, armonía y motivos",
        "Hasta siempre, Robe...",
        "Extremoduro 🤝🏼 Bach",
        "Camarón 🤝 Tabletom 🤝 Extremoduro",
    ],
)
def test_entra_por_titulo(title, vocab):
    ok, why = is_relevant(title, None, vocab=vocab)
    assert ok, f"debería entrar: {title}"
    assert why, "un match sin motivo no es auditable"


def test_la_ley_innata_es_distintiva(vocab):
    """«La ley innata» normaliza a «ley innata» (10 chars): justo en el umbral.

    Si se sube el umbral, el capítulo 1 —cuyo único anclaje es el nombre del
    disco— pasa a señal débil y deja de casar por substring.
    """
    assert len(_n("La ley innata")) == MIN_DISTINCTIVE
    ok, why = is_relevant("LA LEY INNATA (ANÁLISIS) | Capítulo 1: contexto", vocab=vocab)
    assert ok
    assert not any("señal débil" in w for w in why)


# --------------------------------------------------------------------------- #
# Lo que NO debe entrar
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "title",
    [
        "A7X 🤝 SOAD",
        "Ya iba tocando cubrir a Apocalyptica 🤘🔥",
        "EVITA las LESIONES con el CHELO | Ergonomía del violonchelo pt. 1",
        "La diosa del metal sinfónico 💫🔥🧡",
        "ANALIZANDO a SYSTEM OF A DOWN: \"Highway song\" | Tesônica",
        "Mi pequeño homenaje a CHESTER BENNINGTON | Análisis del dolor en sus letras",
        "¿Qué banda me he dejado? Te leo 👀",
        "Probablemente de mis géneros favoritos🤘",
    ],
)
def test_no_entra_lo_ajeno(title, vocab):
    ok, _ = is_relevant(title, None, vocab=vocab)
    assert not ok, f"NO debería entrar: {title}"


# --------------------------------------------------------------------------- #
# La descripción: rescata, pero no cuela palabras corrientes
# --------------------------------------------------------------------------- #
def test_descripcion_rescata_titulo_criptico(vocab):
    """«Deltó!!» no dice nada; su descripción sí habla de Extremoduro."""
    ok, why = is_relevant(
        "Deltó!!",
        "Un repaso al disco de Extremoduro que más me marcó de adolescente",
        vocab=vocab,
        use_description=True,
    )
    assert ok
    assert any("descripción" in w for w in why)


def test_descripcion_ignorada_si_el_canal_no_la_habilita(vocab):
    ok, _ = is_relevant("Deltó!!", "Un disco de Extremoduro", vocab=vocab)
    assert not ok


def test_titulo_corto_no_cuenta_en_la_descripcion(vocab):
    """El falso positivo real: un vídeo sobre Tarja hablando de «su carrera».

    «La Carrera» es una canción del catálogo, pero buscarla en prosa larga
    convierte cualquier biografía musical en material de Extremoduro.
    """
    ok, _ = is_relevant(
        "Llegó el turno de Tarja 👑✨",
        "Repasamos su carrera desde Nightwish hasta hoy",
        vocab=vocab,
        use_description=True,
    )
    assert not ok


def test_titulo_corto_si_cuenta_en_el_titulo(vocab):
    ok, why = is_relevant("Deltoya, disco a disco", None, vocab=vocab)
    assert ok
    assert any("señal débil" in w for w in why), "debe avisar de que es señal frágil"


def test_titulo_corto_exige_palabra_completa(vocab):
    """«Mama» no puede picar dentro de otra palabra."""
    ok, _ = is_relevant("Mamadas de un fan cualquiera", None, vocab=vocab)
    assert not ok


def test_sin_titulo_ni_descripcion(vocab):
    assert is_relevant(None, None, vocab=vocab) == (False, [])


# --------------------------------------------------------------------------- #
# El vocabulario sale de la BD, no de una lista a mano
# --------------------------------------------------------------------------- #
def test_build_vocab_reparte_por_longitud():
    class _FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _FakeDB:
        def __init__(self):
            self._calls = 0

        def query(self, _col):
            self._calls += 1
            # 1ª llamada: canciones. 2ª: álbumes.
            if self._calls == 1:
                return _FakeQuery([("Golfa",), ("Dulce Introducción al Caos",)])
            return _FakeQuery([("La ley innata",)])

    v = build_vocab(_FakeDB())
    assert _n("Dulce Introducción al Caos") in v.distinctive
    assert _n("La ley innata") in v.distinctive
    assert _n("Golfa") in v.short
    assert len(v) == 3
