"""Tests del texto de un post: las slides las escribe alguien, y pasan el gate.

Lo que estos tests vigilan, en una línea: que el carrusel deje de ser un
`re.split()` con «CLAVE 01» encima, y que el texto nuevo NO se publique sin
pasar por las mismas guardas que el caption.

Sin red y sin BD salvo donde hace falta: el LLM se inyecta.
"""
from __future__ import annotations

from app.services.instagram import carousel, editorial, newsroom, tono_guard


def _topic_noticia(**kw) -> dict:
    base = {
        "title": "Milongas Extremas vuelve a Plasencia",
        "headline": "Milongas Extremas vuelve a Plasencia",
        "caption_body": "El grupo toca el sábado en la plaza Mayor.",
        "content_type": "news",
        "corpus": {},
        "summary": "",
    }
    base.update(kw)
    return base


SLIDES_BUENAS = [
    {"kicker": "1996", "text": "Agila salió en 1996 y aquel disco cambió el tamaño "
                               "de los conciertos de Extremoduro para siempre."},
    {"kicker": "QUIÉN TOCA", "text": "Iñaki Antón, Uoho, firma aquí los arreglos que "
                                     "llevan la canción de la acústica al muro."},
]


# --------------------------------------------------------------------------- #
# Las slides redactadas mandan sobre el troceo
# --------------------------------------------------------------------------- #
def test_las_slides_escritas_llegan_al_carrusel():
    specs = carousel.plan(_topic_noticia(slides=SLIDES_BUENAS), "news")
    assert specs is not None
    textos = [s["text"] for s in specs]
    assert SLIDES_BUENAS[0]["text"] in textos
    assert SLIDES_BUENAS[1]["text"] in textos


def test_el_kicker_escrito_sustituye_al_contador():
    """«CLAVE 01» era una etiqueta que no decía nada. Ahora la escribe quien
    escribe la slide."""
    specs = carousel.plan(_topic_noticia(slides=SLIDES_BUENAS), "news")
    kickers = [s.get("kicker") for s in specs if s.get("kicker")]
    assert "1996" in kickers
    assert not any((k or "").startswith("CLAVE") for k in kickers)


def test_sin_slides_escritas_el_troceo_sigue_funcionando():
    """Red de seguridad: sin clave de OpenAI o con el modelo caído, el carrusel
    sale como salía."""
    cuerpo = (
        "El grupo toca el sábado en la plaza Mayor de Plasencia. "
        "Es su tercera visita a la ciudad en dos años. "
        "La entrada es libre hasta completar aforo."
    )
    specs = carousel.plan(_topic_noticia(caption_body=cuerpo), "news")
    assert specs is not None
    assert any((s.get("kicker") or "").startswith("CLAVE") for s in specs)


def test_el_cierre_nunca_se_ampute():
    """El `specs[:MAX_SLIDES]` se comía el closing cuando había desarrollo de
    sobra: el carrusel acababa a media frase, sin CTA y sin firma."""
    muchas = [
        {"kicker": f"K{i}", "text": f"Una frase con datos de {1990 + i} sobre el "
                                    f"disco y su grabación en Madrid número {i}."}
        for i in range(6)
    ]
    specs = carousel.plan(_topic_noticia(slides=muchas), "news")
    assert specs is not None
    assert specs[-1]["layout"] == "closing"
    assert len(specs) <= carousel.MAX_SLIDES


def test_el_cierre_escrito_se_pinta_en_la_ultima_tarjeta():
    specs = carousel.plan(
        _topic_noticia(slides=SLIDES_BUENAS, cierre="Plasencia le sigue debiendo una plaza"),
        "news",
    )
    assert specs[-1]["text"] == "Plasencia le sigue debiendo una plaza"


# --------------------------------------------------------------------------- #
# El gate ve las slides (el hueco por el que entró el post de Guardiola)
# --------------------------------------------------------------------------- #
def test_el_texto_que_ven_las_guardas_incluye_las_slides():
    topic = _topic_noticia(slides=SLIDES_BUENAS, cierre="Una frase de cierre")
    texto = newsroom.texto_publicado(topic)
    assert SLIDES_BUENAS[0]["text"] in texto
    assert SLIDES_BUENAS[1]["text"] in texto
    assert "Una frase de cierre" in texto
    assert topic["headline"] in texto
    assert topic["caption_body"] in texto


def test_el_texto_publicado_ignora_lo_vacio():
    assert newsroom.texto_publicado({"headline": "", "caption_body": "x"}) == "x"


# --------------------------------------------------------------------------- #
# Normalización: una tarjeta a medias se ve más que una tarjeta menos
# --------------------------------------------------------------------------- #
def test_una_slide_demasiado_corta_se_descarta():
    out = editorial._normalizar_slides([{"kicker": "X", "text": "Corta."}])
    assert out == []


def test_una_slide_demasiado_larga_se_descarta():
    largo = "a" * (editorial.SLIDE_MAX_CHARS + 1)
    assert editorial._normalizar_slides([{"kicker": "X", "text": largo}]) == []


def test_un_kicker_que_no_cabe_descarta_la_slide():
    out = editorial._normalizar_slides([
        {"kicker": "UNA ETIQUETA LARGUÍSIMA QUE NO CABE", "text": SLIDES_BUENAS[0]["text"]},
    ])
    assert out == []


def test_dos_slides_que_dicen_lo_mismo_son_una():
    out = editorial._normalizar_slides([SLIDES_BUENAS[0], dict(SLIDES_BUENAS[0])])
    assert len(out) == 1


def test_nunca_mas_de_tres_slides():
    muchas = [
        {"kicker": f"K{i}", "text": f"Frase número {i} con su dato de {1990 + i} y "
                                    f"su nombre propio, Plasencia, dentro."}
        for i in range(8)
    ]
    assert len(editorial._normalizar_slides(muchas)) == editorial.MAX_SLIDES


def test_el_kicker_se_normaliza_a_mayusculas():
    out = editorial._normalizar_slides([{"kicker": "el disco", "text": SLIDES_BUENAS[0]["text"]}])
    assert out[0]["kicker"] == "EL DISCO"


# --------------------------------------------------------------------------- #
# El linter de tono
# --------------------------------------------------------------------------- #
def test_tumba_los_titulares_de_molde_que_se_publicaron():
    """Copiados del log de producción del 21-09-2026."""
    for titular in (
        "Ama, Ama, Ama: Un Canto a la Libertad y el Amor",
        "La evolución musical de Robe: de Extremoduro a su legado",
        "La Evolución Musical de Extremoduro: Un Viaje Sonoro",
        "Extremoduro: La Evolución del Rock Transgresivo en España",
        # Se coló en producción: `content_guard` veta «dejó huella» y esto es
        # el mismo molde en gerundio.
        "El poema de Chinato dejando una huella imborrable en el rock español",
    ):
        v = tono_guard.revisar(titular=titular, comentario="", slides=[], cierre="")
        assert not v.ok, f"debería tumbarse: {titular}"


def test_la_esencia_con_determinante_se_tumba_en_todas_sus_formas():
    """Literales de producción. Los tres primeros los cazaba ya el patrón
    viejo; los tres últimos se le escapaban porque pedía «la esencia» seguida
    de una lista corta de palabras, y bastaba un posesivo o un adjetivo por
    medio para colarse. El de «su esencia pura» salió publicado el 23-09-2026
    en un clip de concierto, que es donde menos se puede interpretar al aire.
    """
    for frase in (
        "La conexión entre la localidad y la esencia del rock será el eje",
        "mantener viva la esencia de la banda y recordar las letras",
        "recordar la esencia de la música que nos une",
        "Robe en su esencia pura, caminando por encima de todo",
        "Para él, 'La ley innata' representaba esa esencia única de cada persona",
        "capturó la esencia cruda y transgresora que querían transmitir",
    ):
        assert tono_guard.moldes_en(frase), f"debería cazarse: {frase}"


def test_deja_pasar_un_texto_con_fundamento():
    """Si la guarda tumba lo bueno, la guarda está mal (mismo criterio que
    `seo_style`). Este texto es el patrón de lo que SÍ queremos publicar."""
    v = tono_guard.revisar(
        titular="Agila cumple treinta años",
        comentario="Lo grabaron en 1996 con Iñaki Antón a la guitarra y salió "
                   "de gira antes de que nadie supiera pronunciarlo.",
        slides=SLIDES_BUENAS,
        cierre="Treinta años y el disco sigue sin envejecer",
    )
    assert v.ok, v.bloqueos


def test_una_slide_sin_ningun_dato_no_pasa():
    vacias = [
        {"kicker": "UNO", "text": "Es una canción que emociona a cualquiera que la "
                                  "escuche con el corazón abierto y de verdad."},
        {"kicker": "DOS", "text": "Habla de cosas que todos hemos sentido alguna vez "
                                  "en la vida, y por eso sigue funcionando hoy."},
    ]
    v = tono_guard.revisar(titular="Algo", comentario="", slides=vacias, cierre="")
    assert not v.ok


def test_un_kicker_contador_se_bloquea():
    v = tono_guard.revisar(
        titular="Agila cumple treinta años",
        slides=[{"kicker": "CLAVE 01", "text": SLIDES_BUENAS[0]["text"]}],
    )
    assert not v.ok
    assert any("contador" in b for b in v.bloqueos)


def test_repetir_el_comentario_en_una_slide_avisa_pero_no_bloquea():
    v = tono_guard.revisar(
        titular="Agila cumple treinta años",
        comentario=SLIDES_BUENAS[0]["text"],
        slides=SLIDES_BUENAS,
    )
    assert v.ok
    assert v.avisos


def test_tiene_ancla_reconoce_un_verso_entrecomillado():
    assert tono_guard.tiene_ancla('Cierra con «dejo las ventanas sin cerrar» y se va')
    assert not tono_guard.tiene_ancla("una frase que no dice absolutamente nada")
