"""Localizar el estribillo en un vídeo de UNA canción (09-10-2026).

Un clip es una canción cortada en su estribillo, y el texto del post es el de
esa canción. Localizar y verificar es el mismo paso: si no se oye el estribillo
de ESA canción, no hay clip.
"""
from __future__ import annotations

from app.services.instagram.estribillo import MAX_CLIP_S, MIN_CLIP_S, localizar

LETRA = [
    "Si te vas, me quedo en esta calle sin salida",
    "buscando una salida que no existe",
    "Que a este bar está cansado ya de despedidas",
    "como un extraterrestre se posa en el suelo",
    "y me ofrece regalos que trae de otros cielos",
]
ESTRIBILLO = ["Que a este bar está cansado ya de despedidas"]


def _s(a, b, t, nsp=0.05):
    return {"start": a, "end": b, "text": t, "no_speech_prob": nsp}


def test_casa_el_estribillo_y_corta_alrededor():
    segs = [
        _s(0, 20, "", 0.95),                                            # intro
        _s(20, 26, "si te vas me quedo en esta calle sin salida"),
        _s(26, 31, "buscando una salida que no existe"),
        _s(31, 37, "como un extraterrestre se posa en el suelo"),
        _s(40, 46, "que a este bar esta cansado ya de despedidas"),
        _s(46, 52, "y me ofrece regalos que trae de otros cielos"),
    ]
    t = localizar(segs, ESTRIBILLO, LETRA)
    assert t is not None and t.verso == ESTRIBILLO[0]
    assert t.start_s == 38.5 and MIN_CLIP_S <= t.end_s - t.start_s <= MAX_CLIP_S
    assert t.tramos_cancion >= 3


def test_otra_cancion_no_da_clip():
    segs = [_s(i * 6, i * 6 + 5, "por la tapia del corral yah yah yah me voy") for i in range(6)]
    assert localizar(segs, ESTRIBILLO, LETRA) is None


def test_sin_estribillo_no_hay_clip_aunque_sea_la_cancion():
    segs = [
        _s(0, 6, "si te vas me quedo en esta calle sin salida"),
        _s(6, 12, "buscando una salida que no existe"),
        _s(12, 18, "como un extraterrestre se posa en el suelo"),
    ]
    assert localizar(segs, ESTRIBILLO, LETRA) is None


def test_un_fragmento_corto_no_cuenta():
    """«¡Vamos Manolo!» casó como verso a 0,80 en los conciertos: lo corto no vale."""
    segs = [_s(i * 3, i * 3 + 2, "despedidas") for i in range(10)]
    assert localizar(segs, ESTRIBILLO, LETRA) is None


def test_lo_marcado_sin_voz_no_cuenta():
    segs = [_s(i * 6, i * 6 + 5, "que a este bar esta cansado ya de despedidas", 0.9)
            for i in range(5)]
    assert localizar(segs, ESTRIBILLO, LETRA) is None


def test_un_bucle_de_whisper_no_prueba_la_cancion():
    """Sobre música Whisper repite la misma frase en bucle: no cuenta como tres."""
    segs = [_s(i * 6, i * 6 + 5, "que a este bar esta cansado ya de despedidas") for i in range(6)]
    assert localizar(segs, ESTRIBILLO, LETRA) is None
