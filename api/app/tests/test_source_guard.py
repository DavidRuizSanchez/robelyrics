"""La voz es nuestra: literales del borrador #40 (/extremoduro, 19-10-2026) que David tumbó."""
from __future__ import annotations

from app.services import source_guard as sg

BORRADOR_40 = [
    "El blog javitojavierito recoge que Extremoduro definió su estilo como rock transgresivo.",
    "Mikel López Iturriaga, en El País, describió un panorama musical tranquilo.",
    "El análisis de Juancares en YouTube describe una canción de Extremoduro.",
    "Juancares señala la presencia de María y Belén, dos voces placentinas.",
    "El blog LaleydeExtremoduro relaciona «Canciones prohibidas» con «Necesito Droga y Amor».",
    "Según el análisis de Juancares en YouTube, Extremoduro la tocó por última vez en 2004.",
]


def test_cada_mencion_del_borrador_40_se_caza():
    for frase in BORRADOR_40:
        assert sg.fuentes_nombradas(frase), frase


def test_robe_se_cita_con_su_medio():
    assert sg.fuentes_nombradas("Robe contó a RockFM que aquel disco le costó la salud.") == []
    assert sg.fuentes_nombradas("En El País, Robe explicó que no volvería a girar.") == []


def test_un_analista_no_se_cuela_por_citar_a_robe():
    assert sg.fuentes_nombradas("Juancares explica que Robe dijo que la odiaba.")


def test_la_prensa_sin_robe_hablando_tampoco():
    assert sg.fuentes_nombradas("Mondo Sonoro lo eligió disco del año.")


def test_frases_normales_no_son_medios():
    for frase in ("Todo el mundo la cantaba en los conciertos.",
                  "Recorrieron el país de punta a punta.",
                  "El público coreó el estribillo entero.",
                  "La historia de Extremoduro empieza en Plasencia.",
                  "Grabaron el material en Madrid."):
        assert sg.fuentes_nombradas(frase) == [], frase


def test_setlist_fm_se_atribuye_porque_sus_terminos_lo_exigen():
    assert sg.fuentes_nombradas("Según setlist.fm, la tocaron en 312 conciertos.") == []


def test_un_enlace_no_es_una_mencion():
    assert sg.fuentes_nombradas(
        "La tocaron en [Plasencia](https://entreinteriores.com/lugares/plasencia).") == []


def test_limpiar_quita_las_frases_y_deja_el_resto():
    texto = ("## El género\n\nExtremoduro se definió como rock transgresivo. "
             "El blog javitojavierito lo sitúa dentro del rock urbano. "
             "El fragmento disponible no identifica el título de la canción.")
    limpio, quitadas = sg.limpiar(texto)
    assert limpio == "## El género\n\nExtremoduro se definió como rock transgresivo."
    assert len(quitadas) == 2


def test_el_heading_no_se_toca():
    limpio, quitadas = sg.limpiar("## La búsqueda de un sonido\n\nTexto.")
    assert limpio.startswith("## La búsqueda de un sonido") and not quitadas


def test_un_enlace_en_el_parrafo_no_arrastra_las_frases_buenas():
    """Visto en la prueba del 19-10-2026: con un enlace en el párrafo se evaluaba la
    línea entera y una sola frase culpable se llevaba también «Decidí»."""
    linea = ("«[Decidí](https://entreinteriores.com/extremoduro/rock-transgresivo/decidi)», "
             "de «Rock Transgresivo», aborda la lucha contra la adversidad. "
             "El blog javitojavierito lo sitúa en el rock urbano.")
    limpio, quitadas = sg.limpiar(linea)
    assert limpio.startswith("«[Decidí](https://entreinteriores.com/extremoduro/")
    assert "aborda la lucha contra la adversidad." in limpio
    assert quitadas == ["El blog javitojavierito lo sitúa en el rock urbano."]


def test_el_metatexto_de_personas_se_quita():
    limpio, quitadas = sg.limpiar("Uoho fue guitarrista. En una formación citada, Extremoduro "
                                  "estaba integrada por Robe y Uoho.")
    assert limpio == "Uoho fue guitarrista." and len(quitadas) == 1


# Miembros y amigos: fuente propia que NO se cita (David, 23-10-2026). Solo Robe.

def test_un_miembro_no_se_cita_con_su_medio():
    for frase in (
        "Uoho contó a RockFM que grabaron Agila en Iruña.",
        "Iñaki Antón, compañero de Robe durante veinte años, contó a RockFM que se iba.",
        "Leiva explicó en la Cadena SER que Robe le cambió la vida.",
        "Uoho dijo a ABC que Robe dijo basta.",
    ):
        culpa = sg.fuentes_nombradas(frase)
        assert culpa and "solo se cita a Robe" in culpa[0][1], frase


def test_robe_sigue_citandose_aunque_nombre_a_otro():
    assert sg.fuentes_nombradas("Robe contó a RockFM que Uoho le enseñó a grabar.") == []
    assert sg.fuentes_nombradas("Robe Iniesta explicó en la Cadena SER que Leiva era familia.") == []


def test_limpiar_quita_la_cita_del_miembro():
    texto = "Agila salió en 1996. Uoho contó a RockFM que la grabaron en Iruña. Fue disco de oro."
    limpio, quitadas = sg.limpiar(texto, nombres=[])
    assert limpio == "Agila salió en 1996. Fue disco de oro."
    assert quitadas == ["Uoho contó a RockFM que la grabaron en Iruña."]
