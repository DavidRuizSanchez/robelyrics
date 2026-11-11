"""Headings humanos, siempre (criterio de David, 10-11-2026).

Los malos son literales de prod de ese día; los buenos, de cómo se reescribieron.
Si alguien toca la guarda y un bueno deja de pasar, la guarda está mal.
"""
import pytest

from app.services import headings, ranking_guard, seo_style

MALOS = [
    (["Paco Doniga antes de Dosis Letal: su etapa en Indecisión Momentánea",
      "El concierto de 1983"], "Paco Doniga"),
    (["La Carrera: Letra y significado", "Cómo suena en Agila"], "La Carrera"),
    (["Mi espíritu imperecedero: Análisis de la letra y su significado", "Cómo suena"],
     "Mi espíritu imperecedero"),
    (["Quién es Jesús Mateos Brea: de los grafitis al grabado",
      "El macromural de Jesús Mateos Brea sobre Robe y Manolo Chinato"], "Jesús Mateos Brea"),
    (["Paco Doniga y el paso de Robe al micrófono", "La dedicatoria de Robe a Paco Doniga",
      "Paco Doniga en Indecisión Momentánea"], "Paco Doniga"),
    # Ninguno lo nombra: también falla (criterio de David, 10-11-2026).
    (["Antes de Dosis Letal", "El concierto de 1983", "La dedicatoria de Robe"], "Paco Doniga"),
]
BUENOS = [
    (["Cuando Paco Doniga entró en Dosis Letal", "El concierto de 1983",
      "Cuando Robe se puso a cantar", "«Cepillo de dientes»"], "Paco Doniga"),
    (["Qué cuenta la letra de «La Carrera»", "Cómo suena en Agila", "En directo"], "La Carrera"),
    (["Del Jazz a la Casa de la Salud", "Ángel Lorenzo, el primer batería (1987)"],
     "Ángel Lorenzo"),
    (["Jesús Mateos Brea, de los grafitis al grabado", "El mural de Robe y Manolo Chinato"],
     "Jesús Mateos Brea"),
]


@pytest.mark.parametrize("hs,sujeto", MALOS)
def test_los_forzados_se_bloquean(hs, sujeto):
    assert not seo_style.heading_verdict(hs, subject=sujeto).ok


@pytest.mark.parametrize("hs,sujeto", BUENOS)
def test_los_humanos_pasan(hs, sujeto):
    v = seo_style.heading_verdict(hs, subject=sujeto)
    assert v.ok, v.motivos


def test_el_nombre_puede_ir_en_uno():
    assert seo_style.heading_verdict(["Quién es Paco Doniga", "El concierto de 1983"],
                                     subject="Paco Doniga").ok


def test_mayuscula_tras_dos_puntos_es_aviso():
    v = seo_style.heading_verdict(["Su obra: Análisis de la letra"], subject="Otro")
    assert v.ok and v.avisos


def test_quitar_el_nombre_del_heading_no_pierde_la_busqueda():
    protegidas = [{"query": "paco doniga dosis letal", "clicks": 3, "position": 8.0}]
    viejo = "Paco Doniga antes de Dosis Letal: su etapa en Indecisión Momentánea"
    nuevo = "Antes de Dosis Letal: Indecisión Momentánea"
    sin = ranking_guard.renombre_permitido(viejo, nuevo, protegidas)
    con = ranking_guard.renombre_permitido(viejo, nuevo, protegidas,
                                           sujeto=frozenset({"paco", "doniga"}))
    assert not sin.ok          # el comportamiento de antes, sin sujeto
    assert con.ok
    # Pero un rename que suelta lo que pedía la búsqueda además del nombre, no pasa.
    assert not ranking_guard.renombre_permitido(viejo, "Sus primeros años", protegidas,
                                                sujeto=frozenset({"paco", "doniga"})).ok


def test_solo_cambian_las_lineas_de_heading():
    b = "intro\n\n## Paco Doniga y Robe\n\ntexto\n\n### sub\n\n## Otra\n\nfin"
    n = headings.reemplazar(b, ["Con Robe", "Otra"])
    assert n == "intro\n\n## Con Robe\n\ntexto\n\n### sub\n\n## Otra\n\nfin"
    assert headings.solo_cambian_headings(b, n)
    assert not headings.solo_cambian_headings(b, n.replace("texto", "texto cambiado"))


def test_proponer_conserva_el_heading_que_perderia_una_busqueda(monkeypatch):
    b = ("## Paco Doniga antes de Dosis Letal: su etapa\n\nuno\n\n"
         "## Paco Doniga y el micrófono\n\ndos")
    monkeypatch.setattr(headings, "reescribir_headings",
                        lambda *a, **k: ["Antes de Dosis Letal", "Sus recuerdos"])
    protegidas = [{"query": "paco doniga microfono", "clicks": 2, "position": 9.0}]
    p = headings.proponer(None, body_md=b, subject="Paco Doniga", protegidas=protegidas)
    assert p.despues == ["Antes de Dosis Letal", "Paco Doniga y el micrófono"]
    assert p.mantenidos and headings.solo_cambian_headings(b, p.body_nuevo)


def test_generate_deep_reescribe_un_esquema_forzado(monkeypatch):
    from scripts.seo import generate_deep

    monkeypatch.setattr(generate_deep, "log", lambda *a, **k: None)
    monkeypatch.setattr(headings, "reescribir_headings",
                        lambda *a, **k: ["Cuando Paco Doniga entró en Dosis Letal",
                                         "Cuando Robe se puso a cantar"])
    outline = [{"heading": "Paco Doniga antes de Dosis Letal: su etapa", "covers": "a"},
               {"heading": "Paco Doniga y el micrófono", "covers": "b"}]
    nuevo = generate_deep._headings_humanos(None, "Paco Doniga", outline)
    assert [s["heading"] for s in nuevo] == ["Cuando Paco Doniga entró en Dosis Letal",
                                             "Cuando Robe se puso a cantar"]
    assert [s["covers"] for s in nuevo] == ["a", "b"]


def test_un_heading_no_puede_meter_un_dato_que_su_seccion_no_dice(monkeypatch):
    """Muestra del 10-11-2026: «Estudios de grabación en Madrid» → «La grabación del
    debut en los estudios M-20», en una sección que no nombra M-20."""
    b = ("## Estudios de grabación en Madrid\n\nExtremoduro grabó varios discos en Madrid.\n\n"
         "## Conciertos icónicos en Madrid: escenarios de leyenda\n\nTocaron en Madrid.")
    monkeypatch.setattr(headings, "reescribir_headings", lambda *a, **k: [
        "La grabación del debut en los estudios M-20", "Los conciertos en la capital"])
    p = headings.proponer(None, body_md=b, subject="Madrid", protegidas=[])
    assert p.despues[0] == "Estudios de grabación en Madrid"     # conservado
    assert p.despues[1] == "Los conciertos en la capital"
    assert any("m-20" in m.lower() or "m 20" in m.lower() for m in p.mantenidos)


def test_se_aplican_las_mejoras_aunque_un_heading_se_quede_por_posicionamiento(monkeypatch):
    """Agila, 10-11-2026: dos headings se quedaban por búsquedas protegidas y la página
    entera dejaba de aplicarse."""
    b = ("## Qué significa «Agila»: el castúo de Robe\n\nEl título es castúo.\n\n"
         "## Las canciones de «Agila»: temas clave del disco\n\nLas canciones clave del disco.")
    monkeypatch.setattr(headings, "reescribir_headings", lambda *a, **k: [
        "El castúo detrás del título", "Las canciones clave del disco"])
    protegidas = [{"query": "agila significado", "clicks": 3, "position": 6.0}]
    p = headings.proponer(None, body_md=b, subject="Agila", protegidas=protegidas)
    assert p.despues == ["Qué significa «Agila»: el castúo de Robe", "Las canciones clave del disco"]
    assert p.veredicto_despues_bloquea and p.aplicable


def test_si_la_primera_propuesta_quita_el_nombre_hay_una_segunda_vuelta(monkeypatch):
    llamadas = []

    def falso(client, subject, headings_, resumenes, *, motivos=None):
        llamadas.append(motivos)
        if len(llamadas) == 1:
            return ["De Sabadell al escenario", "Los discos"]          # sin el nombre
        return ["Albert Pla, de Sabadell al escenario", "Los discos"]

    monkeypatch.setattr(headings, "reescribir_headings", falso)
    b = "## Los Inicios de Albert Pla: De Sabadell\n\nuno\n\n## La Trayectoria de Albert Pla\n\ndos"
    p = headings.proponer(None, body_md=b, subject="Albert Pla", protegidas=[])
    assert len(llamadas) == 2 and any("ningún heading" in m for m in llamadas[1])
    assert p.despues == ["Albert Pla, de Sabadell al escenario", "Los discos"] and p.aplicable


# --- Falsos positivos de la tanda del 11-11-2026 (literales de prod) ---

def test_un_titulo_citado_no_es_title_case():
    v = seo_style.heading_verdict(["Qué cuenta «Relación Convencional»", "Cómo encaja en «Deltoya»"],
                                  subject="Relación Convencional")
    assert v.ok and not v.avisos, v.motivos + v.avisos


def test_el_titulo_de_otra_obra_no_nombra_al_sujeto():
    hs = ["El amor en las canciones de Robe",
          "«Ama, ama, ama y ensancha el alma», un canto a la libertad",
          "Las contradicciones de «Amor castúo»",
          "El deseo en «Menamoro» y «Y rozar contigo»", "El amor en el rock transgresivo"]
    v = seo_style.heading_verdict(hs, subject="Amor", comun=True)
    assert v.ok and not v.avisos, v.motivos + v.avisos


def test_un_tema_se_reconoce_por_la_raiz():
    hs = ["Extremoduro frente al poder en «Estado Policial»", "Qué cuestiona «V Centenario»",
          "El autorretrato político de Robe", "La frustración institucional en «Manué IV»",
          "La decepción de Robe en «Mama»"]
    assert seo_style.heading_verdict(hs, subject="Política e instituciones", comun=True).ok
    # Sin `comun`, el nombre del tema es una etiqueta y nadie la escribe tal cual.
    assert not seo_style.heading_verdict(hs, subject="Política e instituciones").ok


def test_un_tema_repetido_sigue_bloqueando():
    hs = ["La tormenta como paisaje emocional", "Lo que expresa en las letras",
          "La imagen de la tormenta en «Decidí»", "La tormenta que anuncia el final"]
    assert not seo_style.heading_verdict(hs, subject="La tormenta", comun=True).ok


def test_el_nombre_no_cubre_por_prefijo_lo_que_no_es():
    """«Extremoduro» cubría «extremadura» y «Barricada» la errata «barrigada»."""
    for viejo, nuevo, q, suj in [
        ("Las portadas de los discos de Extremoduro", "Quién dibujó las portadas de los discos",
         "extremadura rock", {"extremoduro"}),
        ("El homenaje de Robe a Barricada", "El homenaje de Robe a la banda",
         "barrigada", {"barricada"}),
    ]:
        protegidas = [{"query": q, "clicks": 2, "position": 9.0}]
        assert ranking_guard.renombre_permitido(viejo, nuevo, protegidas,
                                                sujeto=frozenset(suj)).ok


def test_una_palabra_buscada_sigue_protegida():
    protegidas = [{"query": "guerrero significado", "clicks": 4, "position": 7.0}]
    suj = frozenset({"guerrero"})
    viejo = "El Significado de Guerrero: Lucha y Resistencia"
    assert not ranking_guard.renombre_permitido(viejo, "Qué cuenta «Guerrero»", protegidas,
                                                sujeto=suj).ok
    assert ranking_guard.renombre_permitido(viejo, "Qué significa «Guerrero»", protegidas,
                                            sujeto=suj).ok


def test_tercera_vuelta_con_las_palabras_que_se_buscan(monkeypatch):
    llamadas = []

    def falso(client, subject, headings_, resumenes, *, motivos=None):
        llamadas.append(motivos or [])
        if len(llamadas) == 1:
            return ["Qué cuenta «Guerrero»", "De la calma a las explosiones"]
        return ["Qué significa «Guerrero»", "Otra cosa"]

    monkeypatch.setattr(headings, "reescribir_headings", falso)
    b = ("## El Significado de Guerrero: Lucha y Resistencia\n\nLa lucha.\n\n"
         "## De la calma a las explosiones sonoras\n\nSuena.")
    protegidas = [{"query": "guerrero significado", "clicks": 4, "position": 7.0}]
    p = headings.proponer(None, body_md=b, subject="Guerrero", protegidas=protegidas)
    assert len(llamadas) == 2 and any("significado" in m for m in llamadas[1])
    # Solo cambia la posición conservada; la otra se queda con lo de la primera vuelta.
    assert p.despues == ["Qué significa «Guerrero»", "De la calma a las explosiones"]
    assert p.aplicable and not p.veredicto_despues_bloquea


def test_un_nombre_de_dos_letras_tambien_cuenta():
    hs = ["De Fresa al rock duro", "La influencia de Ñu en el rock español"]
    assert seo_style.heading_verdict(hs, subject="Ñu").ok
