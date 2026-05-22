"""Efemérides de Robe Iniesta y Extremoduro.

Eventos «un día como hoy» curados manualmente a partir de información pública
y verificable (discografía, biografía). Se usan como tema/curiosidad cuando el
día tiene poca actualidad noticiosa.

Formato: clave "MM-DD" -> lista de eventos.
"""
from datetime import date

EFEMERIDES = {
    "07-19": [
        "Nace en Plasencia (Cáceres) Roberto Iniesta Ojea, 'Robe', voz y alma "
        "de Extremoduro. El rock español no volvería a ser el mismo.",
    ],
    "01-01": [
        "Extremoduro arranca como banda en Plasencia a finales de los 80, "
        "germen de toda una generación del rock transgresivo.",
    ],
    "10-28": [
        "Se publica 'Rock transgresivo' (1989), el debut de Extremoduro "
        "autofinanciado vendiendo participaciones entre amigos y fans.",
    ],
    "11-15": [
        "'¡Agila!' (1996) consolida a Extremoduro como uno de los grandes "
        "del rock estatal, con himnos como 'So payaso' y 'Jesucristo García'.",
    ],
    "03-10": [
        "'La ley innata' (2008) llega como una obra conceptual en un solo "
        "movimiento de siete partes: Extremoduro en su faceta más ambiciosa.",
    ],
    "05-27": [
        "'Material defectuoso' (2011) se convierte en el último álbum de "
        "estudio de Extremoduro antes de la etapa en solitario de Robe.",
    ],
    "10-24": [
        "Robe publica 'Lo que aletea en nuestras cabezas' (2014), su primer "
        "disco en solitario tras Extremoduro.",
    ],
    "04-23": [
        "'Bajo el hielo el fuego' (2021), doble álbum en solitario de Robe, "
        "una de sus obras más extensas y personales.",
    ],
}

# Curiosidades intemporales (rotación cuando no hay efeméride del día).
CURIOSIDADES = [
    "El nombre 'Extremoduro' nace de unir 'Extremadura' y 'duro' (rock duro): "
    "la tierra y la actitud en una sola palabra.",
    "'Rock transgresivo', el primer disco, se financió vendiendo "
    "participaciones de 1.000 pesetas entre amigos y seguidores.",
    "Iñaki 'Uoho' Antón, guitarrista, fue clave en el sonido de Extremoduro y "
    "coautor de muchas de sus canciones más célebres.",
    "Robe es conocido por su poesía cruda y literaria: muchas de sus letras "
    "se estudian como auténticos textos poéticos contemporáneos.",
    "'So payaso' y 'Jesucristo García' son dos de los himnos más coreados "
    "del rock español en directo.",
    "Robe construyó un estudio en plena naturaleza extremeña para grabar sus "
    "discos en solitario lejos del ruido de la ciudad.",
    "La colaboración de Extremoduro con Fito Cabrales (Platero y Tú) marcó "
    "una de las amistades más célebres del rock estatal.",
    "'La ley innata' es un disco conceptual de un único tema dividido en "
    "siete partes que se escucha como una sinfonía de rock.",
]


def for_today() -> list[str]:
    """Devuelve las efemérides del día actual (lista, posiblemente vacía)."""
    return EFEMERIDES.get(date.today().strftime("%m-%d"), [])


def curiosidad_del_dia() -> str:
    """Curiosidad rotatoria determinista según el día del año."""
    return CURIOSIDADES[date.today().timetuple().tm_yday % len(CURIOSIDADES)]
