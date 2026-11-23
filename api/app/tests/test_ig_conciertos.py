"""Clips de concierto: qué momento es, de qué bolo, y quién habla.

Lo que se blinda aquí es lo que distingue un clip de directo de uno de
entrevista: que no se descarte un solo por no tener letra, que no se publique a
una banda tributo como si fuera Extremoduro, que una fecha no salga de donde no
debe, y que en una entrevista hable el entrevistado y no el locutor.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import VideoClip
from app.services.instagram import concierto_meta as cm
from app.services.instagram import momentos
from app.services.instagram.clip_picker import habla_el_protagonista


@pytest.fixture()
def db():
    """Solo `video_clips`: es lo único que tocan los tests que la piden."""
    engine = create_engine("sqlite://")
    VideoClip.__table__.create(engine)
    with Session(engine) as s:
        yield s


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


def _bloque(*textos, desde=10):
    """Varios tramos seguidos de la misma canción: una canción la nombra un
    bloque, no un segmento suelto (ver `momentos.CONSENSO`)."""
    return [_Seg(desde + i * 4, desde + 4 + i * 4, t) for i, t in enumerate(textos)]


def test_un_verso_repetido_es_el_estribillo():
    ms = momentos.clasificar(_bloque(
        "ama ama ama y ensancha el alma", "dejo las ventanas sin cerrar",
        "y me voy a dar un garbeo"), _catalogo())
    assert ms[0].tipo == "estribillo"
    assert ms[0].cancion == "Interludio"
    # El verso que viaja es el de la BD, no lo que transcribió Whisper.
    assert ms[0].verso == "Ama, ama, ama y ensancha el alma"


def test_la_primera_linea_es_el_arranque():
    ms = momentos.clasificar(_bloque(
        "dejo las ventanas sin cerrar", "y me voy a dar un garbeo",
        "ama ama ama y ensancha el alma"), _catalogo())
    assert ms[0].tipo == "arranque"


def test_un_segmento_suelto_no_nombra_una_cancion():
    """Lo que publicó «El solo de "La Carrera"»: un tramo suelto de 11
    caracteres casó a 0,91 con otra canción y se llevó el nombre."""
    ms = momentos.clasificar([_Seg(10, 14, "dejo las ventanas sin cerrar")], _catalogo())
    assert [m.cancion for m in ms] == [None]
    # Queda como «dudoso»: no se propone, pero corta el bloque.
    assert [m.tipo for m in ms] == ["dudoso"]


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
        *_bloque("dejo las ventanas sin cerrar", "y me voy a dar un garbeo",
                 "ama ama ama y ensancha el alma", desde=0),
        *[_Seg(12 + i * 4, 16 + i * 4, "", no_speech=0.95) for i in range(5)],
        *_bloque("y me voy a dar un garbeo", "ama ama ama y ensancha el alma",
                 "dejo las ventanas sin cerrar", desde=32),
    ]
    solos = [m for m in momentos.clasificar(segs, _catalogo()) if m.tipo == "solo"]
    assert solos and solos[0].cancion == "Interludio"


def test_sin_voz_y_despues_otra_cosa_es_el_final_no_un_solo():
    segs = [
        *_bloque("dejo las ventanas sin cerrar", "y me voy a dar un garbeo",
                 "ama ama ama y ensancha el alma", desde=0),
        *[_Seg(12 + i * 4, 16 + i * 4, "", no_speech=0.95) for i in range(5)],
        _Seg(40, 44, "¡Gracias, Vigo, de verdad, muchísimas gracias!"),
    ]
    ms = momentos.clasificar(segs, _catalogo())
    assert [m.tipo for m in ms if m.cancion] [-1] == "final"


def _con_tramo_sin_voz(textos, *, con_cancion_antes=True):
    antes = (_bloque("dejo las ventanas sin cerrar", "y me voy a dar un garbeo",
                     "ama ama ama y ensancha el alma", desde=0) if con_cancion_antes else [])
    return [*antes,
            *[_Seg(12 + i * 4, 16 + i * 4, t, no_speech=0.75) for i, t in enumerate(textos)],
            *_bloque("y me voy a dar un garbeo", "ama ama ama y ensancha el alma",
                     "dejo las ventanas sin cerrar", desde=12 + len(textos) * 4)]


def test_si_whisper_transcribe_letra_distinta_ahi_se_canta():
    """«El solo de "Nana cruel"» (#524): siete líneas distintas en 28 s, con la
    probabilidad de no-voz en 0,75. Se publicó como solo y se estaba cantando."""
    segs = _con_tramo_sin_voz(["Yo que te espero", "Yo que hice cada segundo",
                               "Otro mundo mejor", "Las noches enteras", "Y no la encuentro"])
    ms = momentos.clasificar(segs, _catalogo())
    assert "solo" not in [m.tipo for m in ms]
    dudoso = [m for m in ms if m.tipo == "dudoso"]
    assert dudoso and "ahí se canta" in dudoso[0].motivos[0] and dudoso[0].cancion is None


def test_whisper_en_bucle_sobre_la_guitarra_sigue_siendo_un_solo():
    """#510: «para que vuelva» cinco veces seguidas es Whisper en bucle, no letra."""
    segs = _con_tramo_sin_voz(["Sopla el viento sin parar", "para que vuelva",
                               "para que vuelva", "para que vuelva", "♪ ♪"])
    solos = [m for m in momentos.clasificar(segs, _catalogo()) if m.tipo == "solo"]
    assert solos and solos[0].cancion == "Interludio"


def test_un_solo_sin_cancion_antes_no_se_propone():
    """Los cuatro que esperaban el 20-11-2026 llevaban por título el del vídeo de
    YouTube: sin canción no hay nada que contar."""
    segs = _con_tramo_sin_voz(["", "", "", "", ""], con_cancion_antes=False)
    ms = momentos.clasificar(segs, _catalogo())
    assert "solo" not in [m.tipo for m in ms]
    assert any(m.tipo == "dudoso" and "no se sabe qué suena" in m.motivos[0] for m in ms)


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


# --------------------------------------------------------------------------- #
# Un estribillo no es lo que se repite: es lo que VUELVE
# --------------------------------------------------------------------------- #
def test_un_verso_concentrado_al_principio_no_es_estribillo():
    """El caso que David rechazó: «El estribillo de "Por encima del bien y del
    mal"» no cantaba el estribillo. El verso más repetido de esa canción está en
    la línea 0 y sus cuatro apariciones caben en las seis primeras de 45
    (dispersión 0,11): es la letanía de entrada."""
    assert momentos.DISPERSION_MIN > 0.11


def test_el_umbral_deja_pasar_un_estribillo_que_abre_la_cancion():
    """«Luce la oscuridad» empieza en la línea 0 y ES el estribillo: se repite
    12 veces a lo largo de toda la canción (dispersión 0,94). Por eso el
    criterio NO puede ser la posición — mirar si abre habría tirado este."""
    assert momentos.DISPERSION_MIN < 0.94


# --------------------------------------------------------------------------- #
# El clip es el momento, no un relleno
# --------------------------------------------------------------------------- #
class _Mom:
    def __init__(self, tipo, ini, fin, cancion=None):
        self.tipo, self.start_s, self.end_s, self.cancion = tipo, ini, fin, cancion
        self.confianza, self.verso, self.motivos = 1.0, None, []


def test_el_bloque_se_queda_en_su_momento():
    from app.services.instagram.clip_picker import _bloque_del_momento

    ms = [
        _Mom("estribillo", 100, 110, "A"),
        _Mom("estribillo", 110, 120, "A"),
        _Mom("habla", 120, 140),           # otro momento: aquí se corta
    ]
    inicio, fin, _frontera, cubiertos = _bloque_del_momento(ms, 0, 600)
    assert (inicio, fin) == (100, 120)
    assert cubiertos == 2


def test_un_bloque_corto_se_completa_solo_con_la_misma_cancion():
    from app.services.instagram.clip_picker import _bloque_del_momento

    ms = [
        _Mom("estribillo", 100, 105, "A"),   # 5 s: por debajo del mínimo
        _Mom("canto", 105, 112, "A"),        # misma canción: vale
        _Mom("canto", 112, 130, "B"),        # otra canción: no
    ]
    inicio, fin, _f, _c = _bloque_del_momento(ms, 0, 600)
    assert inicio == 100
    assert fin == 112, "no se rellena con otra canción"


def test_solo_se_propone_el_primer_tramo_de_cada_bloque():
    """Antes se construía un candidato por tramo, salían tres versiones del
    mismo trozo y el filtro anti-solape decidía por orden de aparición."""
    from app.services.instagram.clip_picker import abre_bloque

    ms = [_Mom("estribillo", 100, 110, "A"), _Mom("estribillo", 110, 120, "A")]
    assert abre_bloque(ms, 0)
    assert not abre_bloque(ms, 1)


# --------------------------------------------------------------------------- #
# Que el vídeo tenga imágenes
# --------------------------------------------------------------------------- #
def test_la_salida_de_freezedetect_se_lee_bien(monkeypatch, tmp_path):
    """Un congelado sin `freeze_end` llega hasta el final del tramo: es
    justamente el caso de una foto quieta, que no «acaba» nunca."""
    from app.services.instagram import video_clips as vcl

    fichero = tmp_path / "c.mp4"
    fichero.write_bytes(b"x")

    class _Proc:
        stderr = "[freezedetect @ 0x1] lavfi.freezedetect.freeze_start: 0\n"

    monkeypatch.setattr(vcl.subprocess, "run", lambda *a, **k: _Proc())
    assert vcl._es_imagen_fija(str(fichero), 20.0) is True


def test_un_congelado_corto_no_marca_el_video(monkeypatch, tmp_path):
    from app.services.instagram import video_clips as vcl

    fichero = tmp_path / "c.mp4"
    fichero.write_bytes(b"x")

    class _Proc:
        stderr = ("lavfi.freezedetect.freeze_start: 2\n"
                  "lavfi.freezedetect.freeze_end: 5\n")

    monkeypatch.setattr(vcl.subprocess, "run", lambda *a, **k: _Proc())
    assert vcl._es_imagen_fija(str(fichero), 20.0) is False


def test_sin_eventos_no_es_imagen_fija(monkeypatch, tmp_path):
    from app.services.instagram import video_clips as vcl

    fichero = tmp_path / "c.mp4"
    fichero.write_bytes(b"x")
    monkeypatch.setattr(vcl.subprocess, "run",
                        lambda *a, **k: type("P", (), {"stderr": ""})())
    assert vcl._es_imagen_fija(str(fichero), 20.0) is False


def test_no_se_propone_dos_veces_la_misma_cancion_del_mismo_concierto(db):
    """Un estribillo suena varias veces en un bolo. Sin esto salen dos clips del
    mismo estribillo del mismo concierto: no solapan, pero en el feed se leen
    como el mismo post repetido. Pasó con «Si te vas…» de Barcelona."""
    from app.services.instagram.clip_picker import _canciones_usadas

    db.add(VideoClip(
        video_id="dQw4w9WgXcQ", url="https://youtu.be/dQw4w9WgXcQ",
        start_s=640.0, end_s=658.0, status="ready",
        subtitle="El estribillo de «Si te vas...» — Barcelona, 08-10-2022",
    ))
    db.commit()

    usadas = _canciones_usadas(db, "dQw4w9WgXcQ")
    assert any("si te vas" in u for u in usadas)


def test_un_clip_retirado_no_bloquea_su_cancion(db):
    """Si se descartó, esa canción vuelve a estar disponible."""
    from app.services.instagram.clip_picker import _canciones_usadas

    db.add(VideoClip(
        video_id="dQw4w9WgXcQ", url="https://youtu.be/dQw4w9WgXcQ",
        start_s=1.0, end_s=20.0, status="retired",
        subtitle="El estribillo de «Golfa» — Madrid, 07-09-2012",
    ))
    db.commit()
    assert _canciones_usadas(db, "dQw4w9WgXcQ") == set()


# --------------------------------------------------------------------------- #
# El caso real: Vigo, 09-11-2024 (post #504, corregido por un seguidor)
# --------------------------------------------------------------------------- #
def _vigo():
    import json
    from pathlib import Path

    from app.services import lyric_guard as lg

    datos = json.loads((Path(__file__).parent / "fixtures" /
                        "vigo_2024_destrozares.json").read_text("utf-8"))
    canciones = []
    for c in datos["canciones"]:
        lineas = [(t, lg.normalize(t)) for t in c["lines"] if t.strip()]
        canciones.append({"title": c["title"], "lines": lineas,
                          "tokens": frozenset(w for _o, n in lineas for w in n.split())})
    segs = [_Seg(s["start_s"], s["end_s"], s["text"], s["no_speech_prob"] or 0.0)
            for s in datos["segmentos"]]
    return segs, momentos.Catalogo(canciones=canciones)


def test_vigo_el_tramo_sin_voz_es_el_final_de_destrozares():
    """Se publicó «El solo de "La Carrera"» sobre 169-202 s. Era el cierre de
    «Destrozares», que suena de 99 a 148 s."""
    segs, cat = _vigo()
    ms = momentos.clasificar(segs, cat)
    tramo = [m for m in ms if m.start_s <= 170 and m.end_s >= 200]
    assert len(tramo) == 1
    assert tramo[0].cancion == "Destrozares"
    assert tramo[0].tipo == "final"


def test_vigo_nadie_nombra_la_carrera_ni_buitre():
    """Un segmento suelto casaba con cada una (0,91 y 1,00)."""
    segs, cat = _vigo()
    nombradas = {m.cancion for m in momentos.clasificar(segs, cat)}
    assert "La Carrera" not in nombradas
    assert "Buitre No Come Alpiste" not in nombradas


def test_vigo_la_letra_mal_transcrita_no_es_robe_hablando():
    """«Liga esa hora» (118 s) está en mitad de «Destrozares»: no es habla."""
    segs, cat = _vigo()
    hablas = [m for m in momentos.clasificar(segs, cat)
              if m.tipo == "habla" and 115 <= m.start_s <= 122]
    assert hablas == []


# --------------------------------------------------------------------------- #
# «Robe, desde el escenario» que no habla (13 clips reales, 17-11-2026)
# --------------------------------------------------------------------------- #
# De los 13 clips «habla» propuestos hasta el 17-11, solo el #530 lo era. Los
# segmentos son los de prod, ±90 s alrededor de cada clip, y el catálogo es el
# trozo mínimo que reproduce la identificación real: la línea ganadora de cada
# tramo y, por canción, las palabras que comparte con los tramos (el prefiltro).
def _clips_habla():
    import json
    from pathlib import Path

    from app.services import lyric_guard as lg

    datos = json.loads((Path(__file__).parent / "fixtures" /
                        "clips_habla_2026_11.json").read_text("utf-8"))
    canciones, estribillos, arranques = [], {}, {}
    for c in datos["canciones"]:
        lineas = [(t, lg.normalize(t)) for t in c["lines"] if t.strip()]
        canciones.append({"title": c["title"], "lines": lineas,
                          "tokens": frozenset(c["palabras"])})
        estribillos.update({lg.normalize(t): c["title"] for t in c["estribillos"]})
        arranques.update({lg.normalize(t): c["title"] for t in c["arranques"]})
    cat = momentos.Catalogo(canciones=canciones, estribillos=estribillos,
                            arranques=arranques)
    casos = []
    for caso in datos["casos"]:
        segs = [_Seg(s["start_s"], s["end_s"], s["text"] or "", s["no_speech_prob"] or 0.0)
                for s in caso["segmentos"]]
        casos.append((caso["queue_id"], tuple(caso["clip"]), segs))
    return casos, cat


def _bloques_de_habla(segs, cat, *, usar_llm=False):
    """Los bloques «habla» que saldrían, con su texto, tal como los arma el picker."""
    from app.services.instagram import clip_picker as cp

    ms = momentos.clasificar(segs, cat)
    fuera = []
    for i, m in enumerate(ms):
        if m.tipo != "habla" or not cp.abre_bloque(ms, i):
            continue
        ini, fin, _f, _c = cp._bloque_del_momento(ms, i, segs[-1].end_s)
        if fin - ini < cp.MIN_S_DIRECTO:
            continue
        texto = " ".join(s.text for s in segs if ini <= s.start_s <= fin)
        ok, _motivo = cp.habla_al_publico(texto, usar_llm=usar_llm)
        if ok:
            fuera.append((ini, fin, texto))
    return fuera


def test_el_ruido_de_whisper_no_es_habla():
    assert momentos.es_ruido("Música")
    assert momentos.es_ruido("y")
    assert momentos.es_ruido("¡Santos!")
    assert momentos.es_ruido("¿Qué te parece?", "¿Qué te parece?", None), "bucle"
    assert momentos.es_ruido("Perdonad, pero se había jodido algo en los cascos") is None


def test_lo_que_casa_sin_consenso_corta_el_bloque():
    """#531: «perdido,» y «¡Gracias!» se pegaban por encima de la letra que casaba
    sin consenso, y salían 39 s de «Robe hablando»."""
    segs = [
        _Seg(0, 4, "¡Vamos Manolo, que os quiero a todos!"),
        _Seg(4, 8, "dejo las ventanas sin cerrar"),        # casa, pero suelto
        _Seg(8, 12, "Gracias Plasencia, sois la leche, de verdad"),
    ]
    tipos = [m.tipo for m in momentos.clasificar(segs, _catalogo())]
    assert tipos == ["habla", "dudoso", "habla"]


def test_un_tramo_cantado_despacio_no_es_habla():
    """#529: un solo tramo de 29 s con 62 caracteres. Hablando salen 9-16 por
    segundo; eso es una estrofa cantada."""
    ms = momentos.clasificar(
        [_Seg(60, 89, "Atraviesa ya la cortina gris, deja de pensar, nunca estás aquí.")],
        _catalogo())
    assert [m.tipo for m in ms] == ["dudoso"]


def test_un_habla_corta_no_se_estira_con_lo_que_venga():
    """#535: «¡Andoites a todo el mundo!» (3 s) se completaba hasta los 10 s
    mínimos con 30 s de «Adiós, cielo azul»."""
    from app.services.instagram.clip_picker import _bloque_del_momento

    ms = [_Mom("habla", 229, 232), _Mom("canto", 260, 273, "Adiós, cielo azul")]
    _i, fin, _f, _c = _bloque_del_momento(ms, 0, 600)
    assert fin == 232


def test_un_hueco_largo_parte_el_momento():
    from app.services.instagram.clip_picker import abre_bloque

    ms = [_Mom("habla", 100, 104), _Mom("habla", 160, 164)]
    assert abre_bloque(ms, 1), "un minuto después ya es otro momento"


@pytest.mark.parametrize("queue_id", [374, 528, 529, 531, 532, 533, 534, 535,
                                      543, 544, 545, 546])
def test_los_clips_que_no_hablaban_ya_no_salen(queue_id):
    """Sin juez (que en un test no hay): solo con las guardas deterministas,
    ningún bloque de habla toca el tramo que se propuso."""
    casos, cat = _clips_habla()
    _qid, (ini, fin), segs = next(c for c in casos if c[0] == queue_id)
    pisan = [b for b in _bloques_de_habla(segs, cat) if b[0] < fin and b[1] > ini]
    # El #532 empieza con algo que puede ser Robe recitando («Yo soy un guerrero
    # pacífico…», 6 s) y entra «Guerrero»: ya no se estira con la canción.
    assert pisan == [], f"#{queue_id} sigue dando habla: {pisan}"


def test_el_clip_que_si_hablaba_sigue_saliendo():
    """#530, Vigo 2024: «Perdonad, pero se había jodido algo en los cascos»."""
    casos, cat = _clips_habla()
    _qid, (ini, fin), segs = next(c for c in casos if c[0] == 530)
    bloques = [b for b in _bloques_de_habla(segs, cat) if b[0] < fin and b[1] > ini]
    assert bloques, "el único habla de verdad no puede caer"
    assert "cascos" in bloques[0][2]
    assert "Qué te parece" not in bloques[0][2], "el bucle de Whisper queda fuera"


def test_sin_juez_el_habla_no_se_da_por_buena(monkeypatch):
    """El post afirma que Robe habla: ante la duda, no."""
    import app.services.news_research as nr
    from app.services.instagram.clip_picker import habla_al_publico

    def _revienta(*a, **k):
        raise RuntimeError("sin red")

    monkeypatch.setattr(nr, "_json", _revienta)
    ok, motivo = habla_al_publico(
        "Perdonad, pero se había jodido algo en los cascos, bueno, esta se la vamos a dedicar")
    assert not ok
    assert "no se ha podido comprobar" in motivo


def test_el_juez_que_dice_canto_tumba_el_clip(monkeypatch):
    import app.services.news_research as nr
    from app.services.instagram.clip_picker import habla_al_publico

    monkeypatch.setattr(nr, "_json", lambda *a, **k: {"que": "canto"})
    ok, _ = habla_al_publico(
        "Yo soy un guerrero pacífico que llama a librar las batallas de puertas adentro")
    assert not ok
