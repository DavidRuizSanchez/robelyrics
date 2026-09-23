"""Clips de concierto: qué momento es, de qué bolo, y quién habla.

Lo que se blinda aquí es lo que distingue un clip de directo de uno de
entrevista: que no se descarte un solo por no tener letra, que no se publique a
una banda tributo como si fuera Extremoduro, que una fecha no salga de donde no
debe, y que en una entrevista hable el entrevistado y no el locutor.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services.instagram import concierto_meta as cm
from app.services.instagram import momentos
from app.services.instagram.clip_picker import habla_el_protagonista


# --------------------------------------------------------------------------- #
# De qué concierto es: nada se inventa
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("titulo,fecha,lugar", [
    ("Extremoduro - Directo Pub El Barco, Palma de Mallorca 17/4/1993",
     date(1993, 4, 17), "Pub El Barco, Palma de Mallorca"),
    ("Robe - Vigo 2024.11.09 (concierto completo)", date(2024, 11, 9), "Vigo"),
    ("ROBE CONCIERTO MAYEUTICA Barcelona 4K 8-10-2022", date(2022, 10, 8), "Barcelona"),
])
def test_la_fecha_y_el_sitio_salen_del_titulo(titulo, fecha, lugar):
    ev = cm.extraer(titulo)
    assert ev.fecha == fecha
    assert ev.lugar == lugar
    assert ev.fuente == "titulo"


def test_sin_datos_no_se_inventa_nada():
    ev = cm.extraer("extremoduro - directo 90s")
    assert ev.fecha is None
    assert ev.anio is None
    assert ev.como_texto() == ""


def test_el_ano_del_titulo_manda_sobre_la_descripcion():
    """Medido: un vídeo titulado «sala Vértigo 1993» traía «12-09-2016» en la
    descripción —cuándo lo subieron— y el post habría fechado el concierto
    veintitrés años tarde."""
    ev = cm.extraer("Extremoduro en Directo (sala Vértigo 1993) INEDITO",
                    "Subido el 12-09-2016 por el canal")
    assert ev.anio == 1993
    assert ev.fecha is None, "no se acepta una fecha de otro año que el título"


def test_una_fecha_absurda_no_cuela():
    assert cm.extraer("Extremoduro directo 1/1/1850").fecha is None
    assert cm.extraer("Extremoduro directo 31/2/1999").fecha is None


@pytest.mark.parametrize("titulo", [
    "PEDRA TRIBUTO A EXTREMODURO en Ciempozuelos",
    "Milongas Extremas - Homenaje a Extremoduro en directo",
    "Banda tributo a Robe en concierto",
])
def test_un_tributo_no_son_ellos(titulo):
    """La web está llena de tributos, y publicarlos como si fueran Extremoduro
    es el mismo fallo de identidad que confundir a dos personas."""
    assert cm.es_tributo(titulo) is not None


def test_un_concierto_de_verdad_no_se_confunde_con_un_tributo():
    assert cm.es_tributo("Extremoduro - Directo en la Plaza Mayor de Caceres 1992") is None


@pytest.mark.parametrize("titulo", [
    "RUEDA DE PRENSA DE ROBE - Presentación Gira de Mayéutica",
    "AMERICANO REACCIONA A EXTREMODURO | DIRECTO 2002",
    "LA VENTA DE ENTRADAS DE ROBE EN MÉRIDA",
])
def test_lo_que_no_es_un_bolo_se_queda_fuera(titulo):
    assert cm.no_es_concierto(titulo) is not None


# --------------------------------------------------------------------------- #
# Qué momento es
# --------------------------------------------------------------------------- #
def _catalogo() -> momentos.Catalogo:
    letra = [
        ("Dejo las ventanas sin cerrar", "dejo las ventanas sin cerrar"),
        ("y me voy a dar un garbeo", "y me voy a dar un garbeo"),
        ("Ama, ama, ama y ensancha el alma", "ama ama ama y ensancha el alma"),
    ]
    return momentos.Catalogo(
        canciones=[{"title": "Interludio", "lines": letra,
                    "tokens": frozenset(w for _o, n in letra for w in n.split())}],
        estribillos={"ama ama ama y ensancha el alma": "Interludio"},
        arranques={"dejo las ventanas sin cerrar": "Interludio"},
    )


class _Seg:
    """Un `SourceSegment` de mentirijilla, con lo que mira el clasificador."""

    def __init__(self, start, end, text, no_speech=0.1):
        self.start_s, self.end_s, self.text = start, end, text
        self.no_speech_prob = no_speech


def test_un_verso_repetido_es_el_estribillo():
    ms = momentos.clasificar(
        [_Seg(10, 14, "ama ama ama y ensancha el alma")], _catalogo())
    assert ms[0].tipo == "estribillo"
    assert ms[0].cancion == "Interludio"
    # El verso que viaja es el de la BD, no lo que transcribió Whisper.
    assert ms[0].verso == "Ama, ama, ama y ensancha el alma"


def test_la_primera_linea_es_el_arranque():
    ms = momentos.clasificar([_Seg(10, 14, "dejo las ventanas sin cerrar")], _catalogo())
    assert ms[0].tipo == "arranque"


def test_lo_que_no_es_letra_es_alguien_hablando():
    """«¡Vamos Manolo!» casaba con un verso a 0,80 en la primera medición, y es
    Robe animando al público. Un texto corto casa con cualquier cosa."""
    ms = momentos.clasificar([_Seg(10, 14, "¡Vamos Manolo, que os quiero a todos!")],
                             _catalogo())
    assert ms[0].tipo == "habla"
    assert ms[0].cancion is None


def test_un_tramo_sin_voz_seguido_es_un_solo():
    """Aquí está la inversión respecto al picker de entrevistas: esto, que allí
    se descarta por no tener texto, es justo lo que se busca."""
    segs = [
        _Seg(0, 4, "dejo las ventanas sin cerrar"),
        *[_Seg(4 + i * 4, 8 + i * 4, "", no_speech=0.95) for i in range(5)],
        _Seg(24, 28, "y me voy a dar un garbeo"),
    ]
    tipos = [m.tipo for m in momentos.clasificar(segs, _catalogo())]
    assert "solo" in tipos


def test_un_silencio_corto_no_es_un_solo():
    segs = [_Seg(0, 4, "dejo las ventanas sin cerrar"),
            _Seg(4, 8, "", no_speech=0.9),
            _Seg(8, 12, "y me voy a dar un garbeo")]
    assert "solo" not in [m.tipo for m in momentos.clasificar(segs, _catalogo())]


def test_un_texto_corto_necesita_casar_mucho_mejor():
    cat = _catalogo()
    _c, _v, _r = momentos.identificar("ama ama", cat)
    assert _c is None, "dos palabras no identifican una canción"


# --------------------------------------------------------------------------- #
# Quién habla (el fallo del primer clip propuesto)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("texto,motivo", [
    ("Bueno, pues esta canción se llama Puntos Suspensivos y nos ha dejado su jubilación.",
     "programa"),
    ("¿Y cómo viviste tú aquello?", "pregunta"),
    ("Robe siempre ha dicho que las letras le salen solas.", "nombra"),
])
def test_el_locutor_no_da_clip(texto, motivo):
    """El primer clip automático que llegó al correo era exactamente el primero
    de estos: el locutor de la SER presentando, no Robe."""
    ok, _ = habla_el_protagonista(texto, usar_llm=False)
    assert not ok


def test_el_entrevistado_si_da_clip():
    ok, _ = habla_el_protagonista(
        "Siempre me ha gustado la poesía y recuerdo leer a Machado con dieciséis años.",
        usar_llm=False,
    )
    assert ok


def test_sin_juez_disponible_no_se_da_por_bueno(monkeypatch):
    """Ante la duda, no. Publicar al locutor es peor que quedarse sin clip."""
    import app.services.news_research as nr

    def _revienta(*a, **k):
        raise RuntimeError("sin red")

    monkeypatch.setattr(nr, "_json", _revienta)
    ok, motivo = habla_el_protagonista("Una frase cualquiera sin señales claras.")
    assert not ok
    assert "no se ha podido comprobar" in motivo
