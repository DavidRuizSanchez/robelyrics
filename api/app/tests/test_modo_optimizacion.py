"""El modo optimización del circuito de oportunidades.

Optimizar una ficha publicada no es lo mismo que escribir una nueva, y la diferencia
no es de gusto: en el circuito hay una persona que ve un antes/después antes de que
nada toque el sitio, y el gate de rigor se diseñó para auto-publicación.

Lo que se blinda aquí (decisión de David, 22-09-2026, tras ver que TODAS las
ampliaciones se tiraban para atrás):

  - **Lo que el editor jefe rechaza sale igual, con el veredicto colgado**, para que
    lo juzgue una persona. Reproduje los rechazos y el juez tenía razón —el texto era
    paja—, así que la válvula informa, no absuelve.
  - **Pero la válvula abre el juicio sobre si merece leerse, no sobre si es verdad.**
    Un verso que no está en la letra sigue bloqueando aunque la válvula esté abierta.
  - **Nada de esto llega a la generación de fichas nuevas**, donde no hay nadie
    mirando antes de publicar.
  - Y las guardas miden el DELTA: la primera versión del guardia de versos bloqueaba
    la ficha de Interludio para siempre por una cita del libreto que YA estaba
    publicada y que no es un verso.
"""
from __future__ import annotations

import pytest

from app.services import seo_style as st
from scripts.seo import augment_deep as ad

# --------------------------------------------------------------------------- #
# Alias: que no se pida contenido que la página ya tiene
# --------------------------------------------------------------------------- #
CUERPO_CON_LETRA = (
    "## Interludio: letra y significado\n\n"
    "«Dejo las ventanas sin cerrar y la puerta abierta». La canción de Robe abre "
    "Mayéutica y enlaza con La ley innata.\n"
)
ALIAS = {"robe": "robe roberto iniesta", "roberto": "robe roberto iniesta",
         "iniesta": "robe roberto iniesta"}


def test_una_pagina_que_dice_robe_responde_a_quien_busca_roberto_iniesta():
    """316 impresiones pedían «contenido» sobre una página que ya tiene la letra: lo
    que no tenía era la forma «Roberto Iniesta», porque el cuerpo dice «Robe»."""
    from app.services.seo_opportunities import classify_queries

    q = [{"query": "letras de roberto iniesta interludio", "impressions": 316,
          "clicks": 0, "position": 7.4}]
    sin = classify_queries(q, body_md=CUERPO_CON_LETRA, meta_title="Interludio",
                           meta_description="La canción de Robe.")
    con = classify_queries(q, body_md=CUERPO_CON_LETRA, meta_title="Interludio",
                           meta_description="La canción de Robe.", alias=ALIAS)
    assert sin["body"], "sin alias, el caso real daba hueco de contenido"
    assert not con["body"], "con alias no falta contenido: la letra está"


def test_sin_alias_el_comportamiento_es_el_de_siempre():
    """Nadie puede activar esto por defecto sin darse cuenta."""
    assert st.expandir_alias(" robe ", None) == " robe "
    assert "roberto" in st.expandir_alias(" robe ", ALIAS)


def test_los_alias_no_se_contagian_a_quien_no_los_nombra():
    assert "roberto" not in st.expandir_alias(" barricada pamplona ", ALIAS)


# --------------------------------------------------------------------------- #
# El material que se busca por la consulta
# --------------------------------------------------------------------------- #
def _pasaje(**kw):
    base = {"fragmento": "Lo que dijo alguien sobre las olas que se rompen.",
            "kind": "youtube_transcript", "author": "Juancares", "title": "Directo",
            "url": "https://youtube.com/x", "score": 0.54, "source_id": 1,
            "chunk_index": 0}
    return {**base, **kw}


def test_un_vecino_semantico_que_no_habla_del_tema_se_descarta(monkeypatch):
    """El caso real: buscando «donde se rompen las olas» entraba a 0.48 un corte de
    Las Mañanas de Radio Nacional. Puntuaba más alto que la entrevista a Chinato."""
    from app.services import corpus_for_queries as cq

    ruido = _pasaje(fragmento="Son las seis, las cinco en Canarias. Las Mañanas de "
                              "Radio Nacional. Enseguida vamos con la actualidad.",
                    score=0.48)
    ok, motivo = cq._es_utilizable(ruido, "donde se rompen las olas significado")
    assert not ok and "preguntaba" in motivo
    bueno = _pasaje(fragmento="viendo romperse las olas, pobre arbolito que he llorado")
    assert cq._es_utilizable(bueno, "donde se rompen las olas significado")[0]


def test_la_prensa_vetada_no_entra_aunque_puntue_alto():
    """Mondo Sonoro, Efe Eme y Rockdelux están fuera del corpus por decisión del
    proyecto, y sus textos siguen indexados de cuando entraban. Rockdelux se coló
    a 0.56 en la primera prueba."""
    from app.services import corpus_for_queries as cq

    p = _pasaje(url="https://rockdelux.com/discos/agila", score=0.9,
                fragmento="Extremoduro Agila olas rompen")
    ok, motivo = cq._es_utilizable(p, "donde se rompen las olas")
    assert not ok and motivo == "medio vetado"


def test_el_material_ajeno_viaja_con_su_atribucion():
    """Un análisis de Juancares no es algo que dijera Robe. Sin saber de quién es,
    no se publica."""
    from app.services import corpus_for_queries as cq

    assert cq.atribucion(_pasaje()) == "análisis de Juancares en YouTube"
    assert cq.atribucion(_pasaje(kind="genius_annotation", author="")) == \
        "una anotación de Genius"
    assert cq.atribucion(_pasaje(kind="loquesea", author="x")) is None
    assert cq.atribucion(_pasaje(kind="prensa", author="")) is None


def test_el_bloque_separa_la_voz_de_robe_del_material_ajeno():
    from app.services import corpus_for_queries as cq

    bloque = cq.bloque_material([
        {**_pasaje(), "consulta": "x", "atribucion": "análisis de Juancares en YouTube"},
        {**_pasaje(kind="robe_interview", author="Robe"), "consulta": "x",
         "atribucion": "una entrevista con Robe"},
    ])
    assert "MATERIAL DE UN TERCERO" in bloque
    assert "LO QUE DIJO ROBE" in bloque
    assert "NUNCA como voz de Robe" in bloque


def test_el_material_de_la_consulta_no_se_cae_del_corte():
    """Va delante y entero: si compite por el hueco con un dossier de 100.000
    caracteres pierde siempre, porque los bloques interpretativos se ensamblan al
    final y son los primeros en caerse."""
    dossier = "relleno " * 20000
    prioritario = "PASAJE QUE RESPONDE A LA CONSULTA"
    salida = ad._relevant_material(dossier, "hint", priority=prioritario)
    assert prioritario in salida[:len(prioritario) + 10] or prioritario in salida
    assert len(salida) <= 12000


# --------------------------------------------------------------------------- #
# El gate, la válvula y lo que nunca se salta
# --------------------------------------------------------------------------- #
class _Verdict:
    def __init__(self, verdict, score, reasons=None, tightened=None):
        self.verdict, self.score = verdict, score
        self.reasons = reasons or []
        self.tightened_body_md = tightened


class _Entidad:
    id = 1
    slug = "guerrero"
    title = "Guerrero"


class _Sc:
    id = 1
    body_md = "## Lo que ya decía\n\nUn cuerpo con hechos reales y comprobables.\n"


class _Q:
    def __init__(self, row):
        self._row = row

    def filter(self, *a, **kw):
        return self

    def first(self):
        return self._row


class _Db:
    def query(self, *a, **kw):
        return _Q(_Sc())


@pytest.fixture()
def motor(monkeypatch):
    """Cablea las piezas caras y deja elegir qué devuelven."""
    estado = {"seccion": ("## Lo nuevo\n\nMaterial real y verificado.", "Lo nuevo"),
              "antes": 60, "despues": 40, "verdict": "reject",
              "bloqueos_antes": [], "bloqueos_despues": []}

    class _Dossier:
        material = "material"
        hard_facts = "hechos"

    monkeypatch.setattr(ad, "gather_entity_dossier", lambda *a, **kw: _Dossier())
    monkeypatch.setattr(ad, "_corpus_gap_section", lambda *a, **kw: estado["seccion"])
    monkeypatch.setattr(ad, "autolink_corpus", lambda body, *a, **kw: body)
    monkeypatch.setattr(ad, "build_corpus_index", lambda db: [])
    monkeypatch.setattr(ad, "load_link_stats", lambda: {})
    # El «después» se reconoce por el texto, no por los kwargs: si se distinguiera
    # por `spotlight` —que solo existe en modo optimización— sin modo las dos
    # llamadas serían idénticas y el test estaría verde sin probar nada.
    monkeypatch.setattr(
        "app.services.editorial_review.review",
        lambda body, **kw: _Verdict(
            estado["verdict"] if "Lo nuevo" in body else "pass",
            estado["despues"] if "Lo nuevo" in body else estado["antes"],
            ["es redundante"]))

    class _Lv:
        def __init__(self, quote):
            self.quote = quote

    class _Rep:
        def __init__(self, bloqueos):
            self.blocking = [_Lv(q) for q in bloqueos]

    monkeypatch.setattr(
        "app.services.lyric_guard.check_lyrics",
        lambda db, texto: _Rep(estado["bloqueos_despues"] if "Lo nuevo" in texto
                               else estado["bloqueos_antes"]))
    monkeypatch.setattr("app.services.corpus_for_queries.material_para_consultas",
                        lambda db, consultas, **kw: [])
    return estado


def _aumentar(estado, optimizar=True):
    modo = ad.ModoOptimizacion(consultas=["como buen guerrero"]) if optimizar else None
    return ad.augment_entity(_Db(), object(), "song", _Entidad(), optimizar=modo)


def test_lo_que_el_editor_rechaza_sale_igual_con_el_veredicto_colgado(motor):
    """La válvula que pidió David: no publica nada, enseña lo que hay."""
    res = _aumentar(motor)
    assert res["noop"] is False
    assert res["rigor"]["forzada"] is True
    assert res["rigor"]["reasons"] == ["es redundante"]
    assert "Lo nuevo" in res["after"]


def test_sin_modo_optimizacion_un_rechazo_sigue_siendo_no_op(motor):
    """La generación de fichas nuevas no se entera de que esto existe: allí no hay
    nadie mirando antes de publicar."""
    res = _aumentar(motor, optimizar=False)
    assert res["noop"] is True
    assert res["after"] == res["before"]
    assert "forzada" not in (res.get("rigor") or {})


def test_un_verso_inventado_bloquea_aunque_la_valvula_este_abierta(motor):
    """La válvula abre el juicio sobre si merece leerse, NO sobre si es verdad."""
    motor["bloqueos_despues"] = ["Los encuentros de un caracol aventurero"]
    res = _aumentar(motor)
    assert res["noop"] is True
    assert res["rigor"]["bloqueo_duro"] is True
    assert "caracol" in res["rigor"]["reasons"][0]


def test_el_guardia_de_versos_mide_el_delta_y_no_el_estado(motor):
    """Interludio cita el libreto del disco —«Mayéutica es una canción concebida como
    una sola obra…»—, que no es un verso y no está en ninguna letra. Midiendo el
    estado final, esa página no podría ampliarse JAMÁS."""
    cita = "Mayéutica es una canción concebida como una sola obra"
    motor["bloqueos_antes"] = [cita]
    motor["bloqueos_despues"] = [cita]
    res = _aumentar(motor)
    assert res["noop"] is False, "lo que ya estaba publicado no puede condenar la ampliación"


def test_una_caida_dentro_del_ruido_del_juez_sale_limpia(motor):
    """Tres pasadas del juez sobre el MISMO texto dieron revise/reject/reject en este
    repo. Un punto menos es ruido de muestreo, no una regresión.

    Con la válvula abierta, la tolerancia no decide si sale —sale igual— sino si sale
    LIMPIA o marcada como rechazada. Mirar solo `noop` dejaría este test verde aunque
    alguien quitara la tolerancia entera.
    """
    motor.update({"antes": 60, "despues": 57, "verdict": "pass"})
    res = _aumentar(motor)
    assert res["noop"] is False
    assert not res["rigor"].get("forzada"), "una caída de 3 puntos no es una regresión"
    # Y sin modo optimización, ese mismo delta sigue tumbando la ampliación.
    assert _aumentar(motor, optimizar=False)["noop"] is True


def test_una_caida_de_verdad_sigue_contando(motor):
    """La tolerancia no es una barra libre: interludio cayó 65→45 y sigue saliendo
    marcada como rechazada, no como limpia."""
    motor.update({"antes": 65, "despues": 45, "verdict": "pass"})
    res = _aumentar(motor)
    assert res["rigor"]["forzada"] is True
