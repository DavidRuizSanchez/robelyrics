"""Tests del guardia de citas de letra (anti-alucinación de versos).

Blindan dos propiedades opuestas:
  1. Un verso INVENTADO atribuido a una canción se BLOQUEA (caso real del incidente).
  2. Un verso REAL con variaciones triviales (comas, acentos, apócope castizo,
     singular/plural, fragmento parcial) NO se bloquea (cero falsos positivos).

Son unitarios: el corpus se inyecta con monkeypatch, no hace falta BD.
"""
from __future__ import annotations

import pytest

from app.services import lyric_guard as lg

# --- Corpus sintético mínimo con letras reales del catálogo ------------------
SO_PAYASO = (
    "Quiero ser tu perro fiel, tu esclavo sin rechistar\n"
    "So payaso y me tiemblan los pies a su lado\n"
    "Me dice que estoy descolorío', la empiezo a besar\n"
    "So cretino y me tiemblan los pies a su lado\n"
)
SALIR = (
    "Tú, harta de tanta duda; yo, de preguntarle al viento\n"
    "Salir, beber, el rollo de siempre\n"
    "Meterme mil rayas, hablar con la gente\n"
    "Y llegar a la cama y joder qué guarrada sin ti\n"
)
SI_TE_VAS = (
    "Si te vas, me quedo en esta calle sin salida\n"
    "buscando una salida que no existe\n"
)
AMA = (
    "Ama, ama, ama y ensancha el alma\n"
    "que el mundo es de los que se atreven a soñar\n"
)


def _corpus():
    return [
        lg._SongLyrics("So Payaso", "Agila", 1996, lg.normalize(SO_PAYASO), True),
        lg._SongLyrics("Salir", "Canciones prohibidas", 1998, lg.normalize(SALIR), True),
        lg._SongLyrics("Si te vas...", "Material defectuoso", 2011, lg.normalize(SI_TE_VAS), True),
        lg._SongLyrics("Ama, Ama, Ama y Ensancha el Alma", "Deltoya", 1992, lg.normalize(AMA), True),
        # Canción SIN letra en el corpus (Genius roto): cita literal no verificable.
        lg._SongLyrics("Standby", "Pedrá", 1995, "", False),
    ]


@pytest.fixture(autouse=True)
def _patch_corpus(monkeypatch):
    monkeypatch.setattr(lg, "_load_songs", lambda db: _corpus())
    monkeypatch.setattr(lg, "_external_verses", lambda: [])


def _statuses(body):
    rep = lg.check_lyrics(None, body)
    return {v.quote: v.status for v in rep.verdicts}, rep


# --------------------------------------------------------------------------- #
# 1. El incidente real: versos inventados deben bloquear
# --------------------------------------------------------------------------- #
def test_verso_inventado_atribuido_bloquea():
    body = (
        'En "So payaso", del álbum Agila, Robe canta: '
        '"Si te vas, te voy a colgar de las piernas, te voy a colgar".'
    )
    _, rep = _statuses(body)
    assert rep.blocking, "el verso inventado de So payaso debía bloquear"
    assert rep.blocking[0].status == "fabricated"


def test_segundo_verso_inventado_bloquea():
    body = (
        'En "Salir", del disco Canciones prohibidas, suena: '
        '"Por una vez, en la vida, quisiera que el alma me saliera de su escondite".'
    )
    _, rep = _statuses(body)
    assert rep.blocking
    assert rep.blocking[0].status == "fabricated"


# --------------------------------------------------------------------------- #
# 2. Anti-falsos-positivos: versos reales con variaciones triviales pasan
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("quote", [
    "Y me tiemblan los pies a su lado",              # literal
    "Y me tiemblan los pies, a su lado",             # coma añadida
    "y me tiemblan los pies a su lado",              # minúscula
    "Me dice que estoy descolorido",                 # apócope castizo → forma plena
])
def test_verso_real_so_payaso_no_bloquea(quote):
    body = f'En "So payaso" Robe canta: "{quote}".'
    _, rep = _statuses(body)
    assert not rep.blocking, f"«{quote}» es un verso REAL y no debía bloquear"


def test_fragmento_parcial_de_verso_real_pasa():
    body = 'En "Salir": "Meterme mil rayas, hablar con la gente".'
    _, rep = _statuses(body)
    assert rep.is_clean


def test_verso_real_atribuido_correctamente_es_ok():
    body = 'En "Si te vas...": "Si te vas, me quedo en esta calle sin salida".'
    smap, _ = _statuses(body)
    assert all(s == "ok" for s in smap.values())


# --------------------------------------------------------------------------- #
# 3. Misatribución: verso real atribuido a la canción equivocada → revisión
# --------------------------------------------------------------------------- #
def test_verso_real_mal_atribuido_va_a_revision():
    # verso de "Salir" atribuido a "So payaso"
    body = 'En "So payaso" Robe canta: "Meterme mil rayas, hablar con la gente".'
    _, rep = _statuses(body)
    assert rep.to_review and rep.to_review[0].status == "misattributed"
    assert rep.to_review[0].matched_song == "Salir"


# --------------------------------------------------------------------------- #
# 4. Cita literal de canción SIN letra en el corpus → bloqueo (parafrasear)
# --------------------------------------------------------------------------- #
def test_cita_de_cancion_sin_letra_bloquea():
    body = 'En "Standby", del disco Pedrá: "un verso cualquiera que no podemos verificar".'
    _, rep = _statuses(body)
    assert rep.blocking and rep.blocking[0].status == "no_lyrics"


# --------------------------------------------------------------------------- #
# 5. Citar el TÍTULO de una canción no es citar un verso → se ignora
# --------------------------------------------------------------------------- #
def test_citar_titulo_no_se_trata_como_verso():
    body = 'No se puede hablar de amor sin mencionar "Ama, ama y ensancha el alma".'
    _, rep = _statuses(body)
    assert rep.is_clean


# --------------------------------------------------------------------------- #
# 6. Cita sin canción cercana (declaración de entrevista) → fuera del guardia
# --------------------------------------------------------------------------- #
def test_cita_sin_cancion_no_es_asunto_del_guardia():
    body = 'En una entrevista de 2020, Robe reflexionaba: "esto es una frase inventada larga".'
    _, rep = _statuses(body)
    assert rep.is_clean


# --------------------------------------------------------------------------- #
# 7. Funciones puras del matcher
# --------------------------------------------------------------------------- #
def test_normalize_apocope_castizo():
    assert lg.normalize("descolorío'") == "descolorio"
    assert lg.normalize("¡Pa' ná!") == "pa na"


def test_best_ratio_subcadena_exacta_es_uno():
    lyric = lg.normalize(SO_PAYASO)
    assert lg.best_ratio(lg.normalize("y me tiemblan los pies a su lado"), lyric) == 1.0


def test_best_ratio_verso_inventado_es_bajo():
    lyric = lg.normalize(SO_PAYASO)
    r = lg.best_ratio(lg.normalize("te voy a colgar de las piernas"), lyric)
    assert r < lg._REVIEW_RATIO


# --------------------------------------------------------------------------- #
# 8. Los slugs dentro de URLs de enlaces no falsean la atribución
# --------------------------------------------------------------------------- #
def test_url_de_enlace_no_falsea_la_atribucion():
    # Verso real de "Salir" atribuido correctamente, pero con un enlace markdown a
    # OTRA canción justo antes: el slug de la URL no debe robar la atribución.
    body = ('En "[Si te vas...](https://x.com/extremoduro/salir/si-te-vas)" y en '
            '"Salir" suena "Meterme mil rayas, hablar con la gente".')
    _, rep = _statuses(body)
    assert not rep.blocking
    assert not any(v.status == "misattributed" for v in rep.to_review)


def test_mask_link_urls_preserva_longitud():
    s = 'texto "[A](https://larga/url/aqui)" fin'
    assert len(lg._mask_link_urls(s)) == len(s)


# --------------------------------------------------------------------------- #
# 9. Completado de versos: un fragmento se expande a la línea completa
# --------------------------------------------------------------------------- #
_AFUEGO_LINE = "Y llega en tu braguita, el amor, de visita"


def _song_lines_corpus():
    return [{
        "title": "A Fuego",
        "lines": [(_AFUEGO_LINE, lg.normalize(_AFUEGO_LINE)),
                  ("otra línea cualquiera del tema", lg.normalize("otra línea cualquiera del tema"))],
        "tokens": frozenset(lg.normalize(_AFUEGO_LINE + " otra linea cualquiera del tema").split()),
    }]


def test_complete_verses_expande_fragmento(monkeypatch):
    monkeypatch.setattr(lg, "_load_song_lines", lambda db: _song_lines_corpus())
    # fragmento con palabras del medio caídas ("el amor")
    body = 'En "A Fuego" suena "en tu braguita, de visita".'
    out = lg.complete_verses(None, body)
    assert _AFUEGO_LINE in out
    assert "en tu braguita, de visita" not in out.replace(_AFUEGO_LINE, "")


def test_complete_verses_no_toca_verso_ya_completo(monkeypatch):
    monkeypatch.setattr(lg, "_load_song_lines", lambda db: _song_lines_corpus())
    body = f'En "A Fuego": "{_AFUEGO_LINE}".'
    assert lg.complete_verses(None, body) == body
