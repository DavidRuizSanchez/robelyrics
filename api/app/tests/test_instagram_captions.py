"""Tests del ensamblado de captions de Instagram.

Los primeros del pipeline de Instagram, que no tenía ninguno. Cubren justo lo que
falló durante meses en producción y que solo se detectó midiendo los posts ya
publicados: la primera línea era idéntica en el 100% de los posts.

No tocan BD ni red: `captions.build` solo usa la sesión para buscar un verso, y
aquí se le pasa el verso ya resuelto (que es lo que hace `publisher.prepare`).
"""
from __future__ import annotations

import re

from app.services.instagram import captions, captions_moldes


def _topic(**kwargs) -> dict:
    """Topic mínimo con el verso ya resuelto (así `build` no toca la sesión)."""
    base = {
        "title": "Un titular cualquiera",
        "category": "Música",
        "summary": "",
        "content_type": "quote",
        "content_key": "quote:line_1",
        "corpus": {},
        "verse": {},
        "tone": "neutral",
    }
    base.update(kwargs)
    return base


# --------------------------------------------------------------------------- #
# El fallo original: la primera línea no puede ser constante
# --------------------------------------------------------------------------- #
def test_primera_linea_varia_entre_posts():
    """El bug medido: 40/40 posts abrían con `🕯️ Día N sin Robe`."""
    primeras = set()
    for i in range(1, 25):
        topic = _topic(
            title=f"Verso número {i} de la prueba",
            content_key=f"quote:line_{i}",
            corpus={"song": "Standby", "album": "Agila", "year": 1996,
                    "artist": "Extremoduro"},
        )
        caption = captions.build(None, topic)
        primeras.add(caption.split("\n")[0])
    # Con 24 posts y 10 moldes de tipo `quote`, deben salir varios distintos.
    assert len(primeras) >= 5, f"solo {len(primeras)} aperturas distintas: {primeras}"


def test_primera_linea_no_es_el_contador():
    caption = captions.build(None, _topic())
    assert "sin Robe" not in caption.split("\n")[0]


def test_el_contador_sigue_estando_al_pie():
    """No se ha eliminado: se ha movido. Importa para el proyecto."""
    caption = captions.build(None, _topic())
    assert "sin Robe" in caption
    assert captions.SERIE_HASHTAG in caption


# --------------------------------------------------------------------------- #
# Hashtags
# --------------------------------------------------------------------------- #
def test_numero_de_hashtags_en_rango():
    """Veníamos de 10-14; el nicho se mueve entre 4 y 7."""
    caption = captions.build(None, _topic(category="Música"))
    # La línea de hashtags es la que tiene varios; el pie lleva el de serie.
    lineas_ht = [ln for ln in caption.split("\n") if ln.count("#") >= 2]
    assert lineas_ht, "no hay línea de hashtags"
    n = lineas_ht[0].count("#")
    assert 3 <= n <= captions.MAX_HASHTAGS, f"{n} hashtags en «{lineas_ht[0]}»"


def test_no_se_usa_robeiniesta():
    """Regla dura del proyecto: nunca «Robe Iniesta», ni como hashtag."""
    topic = _topic(title="Roberto Iniesta y su guitarra", summary="Sobre Iniesta")
    caption = captions.build(None, topic)
    assert "#RobeIniesta" not in caption
    assert "#robeiniesta" not in caption.lower()


# --------------------------------------------------------------------------- #
# Pregunta de cierre y tono
# --------------------------------------------------------------------------- #
def test_incluye_pregunta_de_cierre():
    caption = captions.build(
        None,
        _topic(corpus={"song": "Standby", "album": "Agila", "year": 1996,
                       "artist": "Extremoduro"}),
    )
    assert "?" in caption


def test_tono_sobrio_no_pregunta():
    """En un homenaje una pregunta de ese corte desentona."""
    topic = _topic(
        tone="sober",
        content_type="ephemeris",
        title="Un día como hoy nació Robe",
        summary="Le recordamos, en su memoria.",
    )
    caption = captions.build(None, topic)
    preguntas = [ln for ln in caption.split("\n") if ln.strip().startswith("¿")]
    assert not preguntas, f"pregunta en tono sobrio: {preguntas}"


# --------------------------------------------------------------------------- #
# Determinismo: re-preparar no cambia el texto
# --------------------------------------------------------------------------- #
def test_es_determinista():
    topic = _topic(corpus={"song": "Standby", "album": "Agila", "year": 1996,
                           "artist": "Extremoduro"})
    assert captions.build(None, topic) == captions.build(None, topic)


# --------------------------------------------------------------------------- #
# Moldes: nunca se imprime un hueco sin dato
# --------------------------------------------------------------------------- #
def test_molde_sin_dato_no_deja_hueco():
    """Un molde con {song} no puede salir si no hay canción."""
    for i in range(30):
        h = captions_moldes.hook("quote", {}, f"quote:line_{i}")
        if h is not None:
            assert "{" not in h and "}" not in h
            assert "«»" not in h


def test_molde_usa_el_dato_real():
    ctx = {"song": "So payaso", "album": "Deltoya", "year": 1992,
           "artist": "Extremoduro"}
    vistos = {captions_moldes.hook("quote", ctx, f"k{i}") for i in range(40)}
    # Alguno de los moldes con campos tiene que haber salido con el dato dentro.
    assert any("So payaso" in v or "Deltoya" in v or "1992" in v
               for v in vistos if v)


def test_ningun_molde_afirma_autoria():
    """Robe no firma todas las letras («Ama, ama…» es de Manolo Chinato)."""
    sospechosas = re.compile(
        r"\b(lo escribió|escrito por|de su puño|compuso)\b", re.IGNORECASE
    )
    for tipo, plantillas in captions_moldes.HOOKS.items():
        for tpl in plantillas:
            assert not sospechosas.search(tpl), f"{tipo}: «{tpl}» afirma autoría"


# --------------------------------------------------------------------------- #
# Cuerpo a una frase por línea
# --------------------------------------------------------------------------- #
def test_una_frase_por_linea():
    txt = "Primera frase. Segunda frase. Y la tercera."
    out = captions_moldes.one_sentence_per_line(txt)
    assert out.count("\n\n") == 2


def test_una_frase_por_linea_no_pierde_texto():
    txt = " ".join(f"Frase número {i}." for i in range(1, 15))
    out = captions_moldes.one_sentence_per_line(txt, max_frases=5)
    for i in range(1, 15):
        assert f"Frase número {i}." in out


def test_una_frase_por_linea_vacio():
    assert captions_moldes.one_sentence_per_line("") == ""
    assert captions_moldes.one_sentence_per_line(None) == ""


# --------------------------------------------------------------------------- #
# Los posts de verso no repiten el verso (ya va en la imagen)
# --------------------------------------------------------------------------- #
def test_post_de_verso_no_repite_el_verso():
    verso = "Me juego el tipo mirándote a los ojos"
    topic = _topic(
        title=verso,
        summary="«Standby» · Extremoduro · Agila (1996)",
        content_type="quote",
        corpus={"song": "Standby", "album": "Agila", "year": 1996,
                "artist": "Extremoduro"},
    )
    caption = captions.build(None, topic)
    assert caption.count(verso) == 0, "el verso ya va escrito en la imagen"
    assert "Standby" in caption, "pero sí debe llevar la atribución"


# --------------------------------------------------------------------------- #
# La atribución se re-deriva del corpus, no se arrastra del summary
# --------------------------------------------------------------------------- #
def test_la_atribucion_no_usa_el_summary_viejo():
    """Caso real de producción: un post preparado antes de corregir el catálogo
    decía «Rock Transgresivo (1989)» cuando el disco es de 1994."""
    topic = _topic(
        title="Soy yo el guionista de mi única novela",
        summary="«Emparedado (Rock Transgresivo)» · Extremoduro · Rock Transgresivo (1989)",
        corpus={"song": "Emparedado", "album": "Rock Transgresivo", "year": 1994,
                "artist": "Extremoduro"},
    )
    caption = captions.build(None, topic)
    assert "1989" not in caption, "se está arrastrando el año viejo del summary"
    assert "1994" in caption
    # Y sin el desambiguador interno del catálogo.
    assert "Emparedado (Rock Transgresivo)" not in caption


def test_sin_corpus_cae_al_summary():
    topic = _topic(summary="«X» · Extremoduro · Y (2000)", corpus={})
    assert "«X»" in captions.build(None, topic)
