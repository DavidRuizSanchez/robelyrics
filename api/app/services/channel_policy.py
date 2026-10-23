"""Qué canales de YouTube se pueden usar, y para qué.

Hay dos usos y no piden lo mismo:

- `clip`: REPUBLICAR un tramo en Instagram. Se vetan los canales oficiales, de
  sello y de distribución, porque son los que reclaman derechos. Es la política
  de siempre de `video_clips`, que importa de aquí sin cambiar de comportamiento.
- `corpus`: TRANSCRIBIR para leer. Ahí el canal oficial de Robe o de Extremoduro
  es de lo más fiable que hay, así que no se veta. Sí se vetan los canales de
  solo música (« - Topic», VEVO): no hay nada que transcribir más que la letra.

En los dos modos caen las reacciones y los tributos: el material es de otro (el
vídeo original con el youtuber encima, o una banda que no es Extremoduro), y
meterlo en el corpus es el mismo fallo que confundir a dos personas.

Se comprueba sobre el nombre REAL del canal (el que devuelve la API o yt-dlp).
"""
from __future__ import annotations

from typing import Literal

Modo = Literal["clip", "corpus"]

# Ojo con «reaccion»/«reacts»: el material de esos canales es el vídeo de OTRO
# con su comentario encima, así que un clip de ahí publica al youtuber, no a
# Robe. Salió al proponer: un tramo de «Leo Reaccion» pasó todas las guardas
# porque el audio original sí era de Robe.
_REACCIONES = ("reaccion", "reacción", "reacts", "reaction", "reacciona")

# Lo que reclama derechos al republicar. Solo cuenta en modo clip.
_OFICIALES_Y_SELLOS = (
    "oficial", "official", "vevo", " - topic", "records", "discos",
    "warner", "sony music", "universal music", "dro east west",
)

# Política de clips de siempre, en el mismo orden (el patrón que se devuelve es
# el primero que casa, y los tests y el correo lo enseñan).
CANALES_VETADOS = _REACCIONES + _OFICIALES_Y_SELLOS

# Para el corpus: reacciones, canales de solo música y bandas tributo/karaoke.
CANALES_VETADOS_CORPUS = _REACCIONES + (
    "vevo", " - topic", "tributo", "tribute", "karaoke",
)

# Un canal que se llama EXACTAMENTE como el artista es su canal, aunque no
# ponga «oficial» ni «VEVO» por ningún lado. Salió buscando conciertos: el canal
# «Robe» a secas publica los directos de Mayéutica, y `CANALES_VETADOS` no lo
# tocaba. Comparación exacta a propósito: «Extremoduro Directos» o «Robe y yo»
# son de fans y tienen que seguir valiendo.
_NOMBRES_OFICIALES = ("robe", "extremoduro", "robe iniesta", "roberto iniesta")


def canal_vetado(canal: str | None, modo: Modo = "clip") -> str | None:
    """Devuelve el motivo que veta a este canal para `modo`, o None si vale."""
    c = (canal or "").casefold().strip()
    if not c:
        return None
    if modo == "corpus":
        return next((p for p in CANALES_VETADOS_CORPUS if p in c), None)
    if c in _NOMBRES_OFICIALES:
        return f"el canal se llama como el artista («{canal.strip()}»)"
    return next((p for p in CANALES_VETADOS if p in c), None)


def es_canal_oficial(canal: str | None) -> bool:
    """El canal propio de Robe o de Extremoduro (para el corpus, máxima confianza)."""
    c = (canal or "").casefold().strip()
    if c in _NOMBRES_OFICIALES:
        return True
    return any(n in c for n in ("robe", "extremoduro")) and any(
        o in c for o in ("oficial", "official")
    )


# Medios audiovisuales grandes. NO se vetan —no son discográficas ni canales
# oficiales de artista, y una entrevista de radio o de televisión es justo el
# material que se busca—, pero se señalan en el correo de aprobación: un clip de
# Movistar+ o de RTVE se reclama antes que el de un fan, y quien aprueba merece
# saberlo antes de pulsar. Vetarlos por mi cuenta sería decidir por David.
CANALES_SENSIBLES = (
    "movistar", "rtve", "el país", "el pais", "atresmedia", "antena 3",
    "telecinco", "mediaset", "la sexta", "cadena ser", "cope", "onda cero",
    "rockfm", "canal extremadura", "tve", "netflix", "hbo", "prisa",
)


def canal_sensible(canal: str | None) -> str | None:
    """Medio profesional que conviene mirar dos veces. No veta: avisa."""
    c = (canal or "").casefold()
    return next((p for p in CANALES_SENSIBLES if p in c), None)
