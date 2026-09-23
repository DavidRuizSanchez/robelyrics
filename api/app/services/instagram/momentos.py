"""Qué está pasando en cada tramo de un concierto: ¿cantan, habla, o suena un solo?

El picker de entrevistas no vale aquí, y no por un ajuste de umbrales: mide
CARACTERES POR SEGUNDO y descarta lo que baja de siete «porque ahí hay música o
silencio». En un directo, eso que descarta es justo el solo de guitarra.

Aquí las señales son otras:

  · `no_speech_prob` de Whisper (que hasta ahora se tiraba al guardar): alto =
    no hay voz. Medido sobre tres conciertos reales, 47 de 137 segmentos pasan
    de 0,6 y son exactamente los tramos instrumentales.
  · Lo que se canta, casado contra la LETRA QUE YA ESTÁ EN LA BASE DE DATOS con
    el matcher de `lyric_guard`, que está hecho para letra cantada (se traga los
    apócopes tipo «pa'»). Medido: se identifica el 71% de los segmentos con voz,
    y funciona hasta en una grabación de 1992.
  · El estribillo no está marcado en ningún sitio, pero se deduce: un verso que
    se repite 3+ veces dentro de su canción lo es casi siempre. Son 288 versos
    en 153 canciones.

REGLA DURA DEL MÓDULO: la transcripción de un directo sirve para ELEGIR el
tramo, JAMÁS para afirmar lo que se dijo. Está garbleada por definición (Whisper
sobre música encima de aplausos). Lo que un post afirme sale de la letra de la
BD, del catálogo y de los datos del concierto — nunca de este texto.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import text as sqltext
from sqlalchemy.orm import Session

from app.services import lyric_guard as lg

logger = logging.getLogger(__name__)

# Por encima de esto, Whisper dice que no hay voz. 0,6 lo separa limpio: medido
# sobre los tres conciertos de la prueba, ningún segmento cantado lo supera.
SIN_VOZ = 0.6
# Un texto corto casa con cualquier cosa: «¡Vamos Manolo!» (14 caracteres) se
# coló como verso de «Sol de Invierno» con 0,80 en la primera medición, cuando
# es Robe hablándole al público. Por eso el listón sube cuanto más corto es.
RATIO_LARGO = 0.62
RATIO_CORTO = 0.85
CORTO_CHARS = 25
# Un verso que aparece 3+ veces en su canción es un estribillo, casi siempre.
REPETICIONES_ESTRIBILLO = 3
# Las dos primeras líneas de una canción: su entrada.
LINEAS_DE_ARRANQUE = 2
# Un solo dura lo que dura un solo. Por debajo de 8 segundos no es nada, y por
# encima de 90 ya no sabemos qué es: medido en el concierto de Barcelona 2022,
# una racha sin voz llegó a 994 segundos (16 minutos), que no es un solo sino un
# tramo donde la transcripción no reconoció nada. Proponerlo sería publicar a
# ciegas.
SOLO_MIN_S = 8.0
SOLO_MAX_S = 90.0

TIPOS = ("estribillo", "habla", "solo", "arranque", "canto")


@dataclass
class Catalogo:
    """La letra de casa, preparada para casar contra lo que se oye."""

    canciones: list[dict] = field(default_factory=list)
    estribillos: dict[str, str] = field(default_factory=dict)   # verso norm → canción
    arranques: dict[str, str] = field(default_factory=dict)     # verso norm → canción

    def __bool__(self) -> bool:
        return bool(self.canciones)


@dataclass
class Momento:
    """Un tramo del concierto y qué es. `verso` sale de la BD, no de Whisper."""

    tipo: str
    start_s: float
    end_s: float
    cancion: str | None = None
    verso: str | None = None
    confianza: float = 0.0
    motivos: list[str] = field(default_factory=list)

    @property
    def duracion_s(self) -> float:
        return round(self.end_s - self.start_s, 2)

    def resumen(self) -> str:
        de = f" · {self.cancion}" if self.cancion else ""
        return (f"{self.tipo}{de} · {self.start_s:.0f}-{self.end_s:.0f}s "
                f"({self.duracion_s:.0f}s, {self.confianza:.2f})")


def cargar_catalogo(db: Session) -> Catalogo:
    """Letras, estribillos y arranques. Una vez por pasada, no por vídeo."""
    canciones = lg._load_song_lines(db)

    estribillos: dict[str, str] = {}
    for titulo, texto, _n in db.execute(sqltext(
        """
        select s.title, l.text, count(*) n
        from lines l join songs s on s.id = l.song_id
        where length(l.text) > 12
        group by s.title, l.text
        having count(*) >= :minimo
        """
    ), {"minimo": REPETICIONES_ESTRIBILLO}).all():
        norm = lg.normalize(texto or "")
        if norm:
            estribillos.setdefault(norm, titulo)

    arranques: dict[str, str] = {}
    for titulo, texto in db.execute(sqltext(
        """
        select s.title, l.text
        from lines l join songs s on s.id = l.song_id
        where l.line_index < :n and length(l.text) > 12
        """
    ), {"n": LINEAS_DE_ARRANQUE}).all():
        norm = lg.normalize(texto or "")
        if norm:
            arranques.setdefault(norm, titulo)

    logger.info("[momentos] catálogo: %d canciones · %d estribillos · %d arranques",
                len(canciones), len(estribillos), len(arranques))
    return Catalogo(canciones=canciones, estribillos=estribillos, arranques=arranques)


def identificar(texto: str, catalogo: Catalogo) -> tuple[str | None, str | None, float]:
    """¿De qué canción es esto que se oye? → (canción, verso REAL, confianza).

    El verso que se devuelve es el de la BASE DE DATOS, no el que transcribió
    Whisper: es el que se puede citar en un post.
    """
    qn = lg.normalize(texto or "")
    if len(qn) < 10:
        return None, None, 0.0
    minimo = RATIO_CORTO if len(qn) < CORTO_CHARS else RATIO_LARGO
    qtok = set(qn.split())

    mejor_cancion, mejor_verso, mejor_ratio = None, None, 0.0
    for c in catalogo.canciones:
        # Prefiltro barato: si la canción no tiene ni la mitad de las palabras,
        # no puede contener el verso (ver `lyric_guard._overlap`).
        if lg._overlap(qtok, c["tokens"]) < 0.5:
            continue
        for original, norm in c["lines"]:
            r = lg.best_ratio(qn, norm)
            if r > mejor_ratio:
                mejor_cancion, mejor_verso, mejor_ratio = c["title"], original, r
    if mejor_ratio < minimo:
        return None, None, mejor_ratio
    return mejor_cancion, mejor_verso, mejor_ratio


def _es(verso: str | None, indice: dict[str, str]) -> bool:
    if not verso:
        return False
    return lg.normalize(verso) in indice


def clasificar(segmentos: list, catalogo: Catalogo) -> list[Momento]:
    """Qué es cada segmento. Los instrumentales seguidos se funden en un solo.

    `segmentos` son filas de `SourceSegment` (o cualquier objeto con `start_s`,
    `end_s`, `text` y opcionalmente `no_speech_prob`).
    """
    fuera: list[Momento] = []
    racha: list = []           # instrumentales consecutivos

    def cerrar_racha(cancion: str | None) -> None:
        """Una racha de instrumental entre partes de una canción es un solo."""
        if not racha:
            return
        inicio, fin = racha[0].start_s, racha[-1].end_s
        duracion = fin - inicio
        if SOLO_MIN_S <= duracion <= SOLO_MAX_S:
            fuera.append(Momento(
                tipo="solo", start_s=inicio, end_s=fin, cancion=cancion,
                confianza=min(1.0, duracion / 30.0),
                motivos=[f"{len(racha)} tramos seguidos sin voz"],
            ))
        elif duracion > SOLO_MAX_S:
            logger.debug("[momentos] %.0fs sin voz en %s: demasiado para ser un "
                         "solo, no se propone", duracion, cancion or "?")
        racha.clear()

    ultima_cancion: str | None = None
    for seg in segmentos:
        sin_voz = (getattr(seg, "no_speech_prob", None) or 0.0) > SIN_VOZ
        texto = (getattr(seg, "text", "") or "").strip()
        if sin_voz or not texto:
            racha.append(seg)
            continue

        cancion, verso, ratio = identificar(texto, catalogo)
        cerrar_racha(cancion or ultima_cancion)

        if cancion is None:
            # Hay voz y no es ninguna letra: alguien está hablando. En un
            # concierto, eso suele ser Robe entre canciones.
            fuera.append(Momento(
                tipo="habla", start_s=seg.start_s, end_s=seg.end_s,
                confianza=0.5, motivos=["voz que no casa con ninguna letra"],
            ))
            continue

        ultima_cancion = cancion
        if _es(verso, catalogo.estribillos):
            tipo, motivo = "estribillo", "verso que se repite 3+ veces en su canción"
        elif _es(verso, catalogo.arranques):
            tipo, motivo = "arranque", "es de las primeras líneas de la canción"
        else:
            tipo, motivo = "canto", "casa con la letra"
        fuera.append(Momento(
            tipo=tipo, start_s=seg.start_s, end_s=seg.end_s, cancion=cancion,
            verso=verso, confianza=ratio, motivos=[motivo],
        ))

    cerrar_racha(ultima_cancion)
    return fuera
