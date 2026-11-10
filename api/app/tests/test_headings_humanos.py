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
    (["Paco Doniga y el paso de Robe al micrófono", "La dedicatoria de Robe a Paco Doniga"],
     "Paco Doniga"),
]
BUENOS = [
    (["Antes de Dosis Letal: Indecisión Momentánea", "El concierto de 1983",
      "Cuando Robe se puso a cantar", "«Cepillo de dientes»"], "Paco Doniga"),
    (["Qué cuenta la letra", "Cómo suena en Agila", "En directo"], "La Carrera"),
    (["Del Jazz a la Casa de la Salud", "El primer batería (1987)"], "Ángel Lorenzo"),
    (["De los grafitis al grabado", "El mural de Robe y Manolo Chinato"], "Jesús Mateos Brea"),
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
                        lambda *a, **k: ["Antes de Dosis Letal", "Cuando Robe se puso a cantar"])
    outline = [{"heading": "Paco Doniga antes de Dosis Letal: su etapa", "covers": "a"},
               {"heading": "Paco Doniga y el micrófono", "covers": "b"}]
    nuevo = generate_deep._headings_humanos(None, "Paco Doniga", outline)
    assert [s["heading"] for s in nuevo] == ["Antes de Dosis Letal", "Cuando Robe se puso a cantar"]
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
