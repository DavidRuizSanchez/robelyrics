"""Tests del detector de omisiones en textos sobre Robe.

Los casos NO son inventados: salen de los dos artículos publicados el 21-09-2026
que destaparon el problema. Uno recorría la discografía entera de Extremoduro y
terminaba en «Mayéutica» (2021) sin decir que Robe había muerto; el otro daba
«Rock Transgresivo» (1994) como disco de debut.

El detector tiene dos formas de fallar y las dos son caras: si se queda corto,
vuelve a colarse un texto incompleto; si se pasa, retiene piezas buenas y el
blog se para (ya pasó once días en este proyecto por un gate demasiado duro).
Por eso hay tantos controles de «esto NO debe disparar» como de lo contrario.
"""
from __future__ import annotations

from app.services import sensitive_topics as st

CATALOGO = [
    "Tú en tu casa, nosotros en la hoguera", "Deltoya", "¿Dónde están mis amigos?",
    "Rock Transgresivo", "Pedrá", "Agila", "Canciones prohibidas",
    "Yo, minoría absoluta", "La ley innata", "Material defectuoso",
    "Para todos los públicos", "Mayéutica", "Se nos lleva el aire",
]

# Extracto real del post #58, tal cual se publicó.
POST_58 = """## Discografía de Extremoduro: Evolución y Obras Clave
Su debut, 'Tú en tu casa, nosotros en la hoguera' (1990), presentó un estilo crudo.
'Pedrá' (1995), un álbum de una única canción de 29 minutos. 'Agila' (1996) supuso
el salto comercial. 'La ley innata' (2008) fue un álbum conceptual.
## La Disolución de Extremoduro y el Legado de Robe
El 18 de diciembre de 2019, Extremoduro anunció su disolución definitiva. La gira
de despedida fue cancelada en agosto de 2021 debido a la pandemia. Robe siguió
explorando su creatividad con proyectos en solitario, como su disco "Mayéutica"
lanzado en 2021."""


# --- Lo que SÍ debe disparar ------------------------------------------------ #
def test_el_post_real_que_destapo_el_problema_se_marca():
    assert st.es_trayectoria(kind="evergreen", subject="Extremoduro",
                             body_md=POST_58, titulos_catalogo=CATALOGO)
    assert not st.menciona_fallecimiento(POST_58)


def test_una_gira_de_despedida_no_es_haber_contado_que_murio():
    """El falso negativo que tuvo este detector en su primera versión: reutilizaba
    la regex de TONO de Instagram, que marca «despedida», «homenaje» y «tributo».
    Con ella, el post #58 pasaba por bueno porque hablaba de una gira."""
    texto = "La gira de despedida de 2019 se canceló. Hubo homenajes y un tributo."
    assert st.menciona_fallecimiento(texto) is False


def test_caza_el_debut_equivocado():
    texto = "Extremoduro debutó en 1994 con el álbum 'Rock Transgresivo'."
    assert st.afirma_debut_erroneo(texto)


def test_caza_la_disolucion_mal_fechada():
    assert st.afirma_disolucion_erronea("La banda se disolvió en 2018.")


# --- Lo que NO debe disparar ------------------------------------------------ #
def test_el_analisis_de_un_verso_no_tiene_que_hablar_de_la_muerte():
    """Lo que evita que esto se convierta en un gate que lo retiene todo."""
    texto = ("Robe canta aquí sobre la máscara. El verso «y me hice pequeñito» "
             "recorre la canción y explica su forma.")
    assert not st.es_trayectoria(kind="spotlight", subject="So payaso",
                                 body_md=texto, titulos_catalogo=CATALOGO)


def test_un_texto_que_ya_lo_cuenta_no_se_marca():
    texto = ("Repaso a Deltoya (1992), Agila (1996) y La ley innata (2008). "
             "Robe falleció el 10 de diciembre de 2025.")
    assert st.menciona_fallecimiento(texto)


def test_el_debut_bien_contado_no_se_marca():
    texto = ("Su debut fue «Tú en tu casa, nosotros en la hoguera» (1990); "
             "«Rock Transgresivo» (1994) es la regrabación que lo sustituyó.")
    assert not st.afirma_debut_erroneo(texto)


def test_la_disolucion_bien_fechada_no_se_marca():
    assert not st.afirma_disolucion_erronea(
        "Extremoduro anunció su disolución el 18 de diciembre de 2019."
    )


def test_hablar_de_otra_banda_no_entra_en_el_perimetro():
    texto = ("Barricada publicó varios discos entre 1983 y 1996, con giras por "
             "todo el país y cambios de formación.")
    assert not st.es_trayectoria(kind="band", subject="Barricada",
                                 body_md=texto, titulos_catalogo=CATALOGO)


# --- Discografía incompleta -------------------------------------------------- #
class _Album:
    def __init__(self, title, year):
        self.title, self.year, self.kind = title, year, "studio"


class _DB:
    def __init__(self, filas):
        self._filas = filas

    def execute(self, _s):
        filas = self._filas

        class _R:
            def all(self_inner):
                return filas

        return _R()


def _db_catalogo():
    return _DB([(_Album(t, 1990 + i), "extremoduro") for i, t in enumerate(CATALOGO)])


def test_detecta_los_discos_que_faltan_cuando_se_esta_enumerando():
    texto = ("Deltoya, Pedrá, Agila, La ley innata y Material defectuoso marcaron "
             "su sonido a lo largo de los años.")

    faltan = st.discos_no_citados(_db_catalogo(), texto)

    assert any("Se nos lleva el aire" in f for f in faltan)


def test_mencionar_dos_discos_de_pasada_no_es_enumerar_discografia():
    """Sin este freno, cualquier texto que nombre un par de discos se llenaría de
    avisos pidiéndole la discografía entera."""
    texto = "En Agila (1996) y en Pedrá (1995) ya estaba todo lo que vendría luego."

    assert st.discos_no_citados(_db_catalogo(), texto) == []


# --- Informe completo -------------------------------------------------------- #
def test_el_informe_manda_a_revision_solo_por_la_omision():
    rep = st.revisar(_db_catalogo(), kind="evergreen", subject="Extremoduro",
                     body_md=POST_58)

    assert rep.necesita_revision
    assert rep.omite_fallecimiento
    assert any("falleció" in m for m in rep.motivos)


def test_una_errata_de_datos_no_retiene_la_pieza():
    """Un disco que falta o una fecha mal se avisan, pero no justifican frenar
    una pieza entera: eso es una errata, no un texto que engaña al lector."""
    texto = ("Deltoya, Pedrá, Agila, La ley innata y Material defectuoso. "
             "Robe falleció en diciembre de 2025.")

    rep = st.revisar(_db_catalogo(), kind="evergreen", subject="Extremoduro",
                     body_md=texto)

    assert rep.hay_erratas
    assert not rep.necesita_revision


# --- Calibración contra las 352 piezas publicadas ---------------------------- #
def test_la_ficha_de_un_colaborador_no_lleva_el_obituario_de_robe():
    """Calibrado en dos vueltas contra producción. Contando menciones en el
    cuerpo se marcaban 240 de 352 piezas; mirando el título seguían entrando las
    fichas de Woody Amores o Ara Malikian, cuyo meta-título dice «de Robe». Quien
    manda es el slug: dice de quién es la página, no a quién cita."""
    cuerpo = ("Woody Amores tocó con Robe en Extremoduro durante años. Participó "
              "en Deltoya, Pedrá, Agila y Canciones prohibidas, y su forma de "
              "tocar marcó el sonido de la banda en aquella época.")

    assert not st.es_trayectoria(
        kind="person", subject="Woody Amores, colaborador de Robe",
        body_md=cuerpo, titulos_catalogo=CATALOGO, entity_slug="woody-amores",
    )


def test_la_ficha_de_robe_si_entra_en_el_perimetro():
    assert st.en_perimetro("lo que sea", "", entity_slug="robe-iniesta")
    assert st.en_perimetro("lo que sea", "", entity_slug="extremoduro")


def test_citar_un_par_de_discos_no_es_recorrer_una_trayectoria():
    """Sin este freno, cualquier ficha de canción que nombre tres discos pediría
    el obituario. La señal es enumerar obra de verdad o titularlo."""
    cuerpo = "La canción aparece en Agila (1996), como Pedrá (1995) y Deltoya (1992)."

    assert not st.es_trayectoria(kind="song", subject="Extremoduro", body_md=cuerpo,
                                 titulos_catalogo=CATALOGO, entity_slug="so-payaso")


def test_un_titular_con_legado_no_convierte_un_analisis_en_una_biografia():
    """Tercera calibración, revisando a mano los 11 posts marcados: salieron un
    análisis de «Ama, ama, ama», otro de «La ley innata» y una noticia sobre una
    banda que versiona a Extremoduro. Los tres llevaban un titular con «legado» o
    «evolución» y ninguno recorría nada. Un encabezado así solo cuenta si además
    el texto abarca varios discos."""
    analisis = ("## El Manifiesto del Amor y su legado\n\n«Ama, ama, ama y ensancha "
                "el alma», del disco Deltoya (1992), es una de las canciones más "
                "icónicas. Robe desafía las normas sociales.")

    assert not st.es_trayectoria(kind="evergreen", subject="Extremoduro",
                                 body_md=analisis, titulos_catalogo=CATALOGO)


def test_un_recorrido_de_verdad_sigue_disparando():
    """La otra mitad: cuatro discos ya es enumerar obra, con titular o sin él."""
    recorrido = ("Deltoya (1992), Pedrá (1995), Agila (1996) y La ley innata "
                 "(2008) marcan las etapas de la banda.")

    assert st.es_trayectoria(kind="evergreen", subject="Extremoduro",
                             body_md=recorrido, titulos_catalogo=CATALOGO)


# --- Lo que NO es una mención de disco --------------------------------------- #
# Cuarta calibración, con el post #59 delante (24-09-2026). El análisis de UNA
# canción quedó retenido por «recorrer la trayectoria»: sumaba cuatro discos, el
# suelo que dispara el gate, y dos de los cuatro no eran menciones. El módulo dice
# que el análisis de una canción no debe disparar; esto es lo que hacía que sí.

POST_59 = """## Análisis de la Letra de 'De Acero (En Directo)'

La canción "[De Acero](https://entreinteriores.com/extremoduro/deltoya/de-acero)
(En Directo)", incluida en el disco *Iros todos a tomar por culo* de Extremoduro,
examina la tensión entre una fachada de dureza y una fragilidad interna.

Este elemento aparece en varias canciones de Extremoduro, como en "Pedrá" y
"Standby", reflejando la búsqueda de libertad. "Standby", del álbum *Yo, minoría
absoluta* (2002), también toca el concepto de el viento."""

CANCIONES = {st._norm(t) for t in ("Pedrá", "Standby", "De Acero", "Deltoya", "Agila")}


def test_el_slug_de_una_url_no_es_una_mencion_de_disco():
    """`/extremoduro/deltoya/de-acero` no nombra *Deltoya*: es el enlace de la
    canción. `lyric_guard` enmascara las URLs desde que un slug falseaba la
    atribución de un verso; aquí contaba como disco citado."""
    cuerpo = ('La canción "[De Acero](https://entreinteriores.com/extremoduro/'
              'deltoya/de-acero)" habla de la dureza.')

    assert "Deltoya" not in st.discos_citados(cuerpo, CATALOGO, CANCIONES)


def test_una_cancion_que_se_llama_como_un_disco_no_cuenta_como_disco():
    """«Pedrá» es disco de 1995 y también canción. Si el texto cita la canción,
    no está nombrando el disco."""
    cuerpo = 'Aparece en varias canciones, como en "Pedrá" y "Standby".'

    assert "Pedrá" not in st.discos_citados(cuerpo, CATALOGO, CANCIONES)


def test_pero_si_el_texto_lo_presenta_como_disco_si_cuenta():
    """El otro lado: en cursiva, con «disco» delante o con su año detrás, es el
    disco. Sin esto, dejaríamos de contar discos citados de verdad."""
    assert "Pedrá" in st.discos_citados("Escuchó *Pedrá* entero.", CATALOGO, CANCIONES)
    assert "Pedrá" in st.discos_citados("el disco Pedrá", CATALOGO, CANCIONES)
    assert "Pedrá" in st.discos_citados("Pedrá (1995)", CATALOGO, CANCIONES)


def test_el_analisis_de_una_cancion_ya_no_se_retiene():
    """El caso real: dos discos de contexto, un slug y una canción homónima."""
    assert not st.es_trayectoria(kind="spotlight", subject="Extremoduro",
                                 body_md=POST_59, titulos_catalogo=CATALOGO,
                                 titulos_cancion=CANCIONES)


def test_el_post_58_sigue_marcado_con_el_criterio_nuevo():
    """REGRESIÓN, no negociable: el artículo que motivó el gate recorría la
    discografía de verdad y omitía la muerte. Tiene que seguir cayendo."""
    assert st.es_trayectoria(kind="evergreen", subject="Extremoduro",
                             body_md=POST_58, titulos_catalogo=CATALOGO,
                             titulos_cancion=CANCIONES)


def test_un_titulo_enlazado_al_DISCO_si_cuenta_aunque_sea_tambien_cancion():
    """La URL desambigua y está ahí: `/extremoduro/deltoya` es el disco y
    `/extremoduro/deltoya/de-acero` una canción suya. Sin mirarla, un texto que
    repasa la obra enlazando cada disco dejaba de contar como recorrido."""
    disco = 'En "[Deltoya](https://entreinteriores.com/extremoduro/deltoya)" ya estaba todo.'
    cancion = ('En "[De Acero](https://entreinteriores.com/extremoduro/deltoya/de-acero)" '
               'se ve la dureza.')

    assert "Deltoya" in st.discos_citados(disco, CATALOGO, CANCIONES)
    assert "Deltoya" not in st.discos_citados(cancion, CATALOGO, CANCIONES)
