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
# Un verso que aparece 3+ veces en su canción es CANDIDATO a estribillo.
REPETICIONES_ESTRIBILLO = 3
# Pero repetirse no basta: un estribillo es el que VUELVE. Se mide cuánto se
# reparten sus apariciones por la canción, `(última - primera) / nº de líneas`.
#
# Salió de un clip que David rechazó: «El estribillo de "Por encima del bien y
# del mal"» no cantaba el estribillo. El verso más repetido de esa canción
# («Todo lo que no está en ti», 4 veces) está en la LÍNEA 0 y sus cuatro
# apariciones caben en las seis primeras de 45 → dispersión 0,11. Es la letanía
# de entrada, no el estribillo.
#
# Medido sobre el catálogo entero, y por eso el criterio NO es la posición:
#   «Todo lo que no está en ti»    4 rep · 0,11  ← el fallo
#   «Luce la oscuridad»           12 rep · 0,94  ← estribillo, y ABRE la canción
#   «Siempre en estado de espera»  5 rep · 0,95
#   «Como buen guerrero»           5 rep · 0,97
# Mirar si abre la canción habría tirado los tres últimos. Con 0,35 se caen 83
# de los 334 versos repetidos: uno de cada cuatro no era un estribillo.
DISPERSION_MIN = 0.35
# Las dos primeras líneas de una canción: su entrada.
LINEAS_DE_ARRANQUE = 2
# Un solo dura lo que dura un solo. Por debajo de 8 segundos no es nada, y por
# encima de 90 ya no sabemos qué es: medido en el concierto de Barcelona 2022,
# una racha sin voz llegó a 994 segundos (16 minutos), que no es un solo sino un
# tramo donde la transcripción no reconoció nada. Proponerlo sería publicar a
# ciegas.
SOLO_MIN_S = 8.0
SOLO_MAX_S = 90.0

TIPOS = ("estribillo", "habla", "solo", "final", "arranque", "canto")


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
    descartados = 0
    for titulo, texto, _n, dispersion in db.execute(sqltext(
        """
        with largo as (
            select song_id, max(line_index)::float + 1 as lineas
            from lines group by song_id
        )
        select s.title, l.text, count(*) as n,
               (max(l.line_index) - min(l.line_index)) / max(largo.lineas) as dispersion
        from lines l
        join songs s on s.id = l.song_id
        join largo on largo.song_id = l.song_id
        where length(l.text) > 12
        group by s.title, l.text
        having count(*) >= :minimo
        """
    ), {"minimo": REPETICIONES_ESTRIBILLO}).all():
        norm = lg.normalize(texto or "")
        if not norm:
            continue
        if (dispersion or 0) < DISPERSION_MIN:
            # Se repite, pero no vuelve: está concentrado en un tramo. Sigue su
            # camino normal (si abre la canción será `arranque`, que es lo que
            # es y tiene su propio título de post).
            descartados += 1
            continue
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

    logger.info(
        "[momentos] catálogo: %d canciones · %d estribillos · %d arranques "
        "(%d versos repetidos descartados por estar concentrados)",
        len(canciones), len(estribillos), len(arranques), descartados,
    )
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


# Consenso: una canción no la nombra UN segmento, la nombra un bloque. El
# 08-11-2026 se publicó «El solo de "La Carrera"» en Vigo y un seguidor lo
# corrigió: era el final de «Destrozares». Reproducido con sus segmentos:
# seis tramos seguidos casaban con «Destrozares» (0,88-1,00), luego «Si la
# suerte» casó con «Buitre no come alpiste» (1,00) y «No me queda», 11
# caracteres, con «La Carrera» (0,91). El solo heredaba la canción del ÚLTIMO
# segmento suelto. Ahora un segmento solo nombra su canción si, en su ventana,
# esa canción tiene al menos `CONSENSO` segmentos y es mayoría.
CONSENSO = 3
VENTANA_CONSENSO_S = 60.0
# Un tramo sin voz hereda la canción del bloque aceptado que tiene justo antes,
# si está a menos de esto. En Vigo, «Destrozares» acaba a 139 s y el tramo sin
# voz empieza a 169 s.
HEREDA_MAX_GAP_S = 45.0


def _consenso(crudo: list[tuple]) -> list[str | None]:
    """Por cada entrada de `crudo`, la canción ACEPTADA (o None).

    `crudo`: (clase, seg, cancion, verso, ratio), clase en voz|sin_voz.
    """
    ident = [(i, e[1], e[2]) for i, e in enumerate(crudo) if e[0] == "voz" and e[2]]
    aceptada: list[str | None] = [None] * len(crudo)
    for i, seg, cancion in ident:
        ventana = [c for _j, s2, c in ident
                   if abs(s2.start_s - seg.start_s) <= VENTANA_CONSENSO_S]
        votos = ventana.count(cancion)
        if votos >= CONSENSO and votos * 2 > len(ventana):
            aceptada[i] = cancion
    return aceptada


def clasificar(segmentos: list, catalogo: Catalogo) -> list[Momento]:
    """Qué es cada segmento. Los instrumentales seguidos se funden en un tramo.

    `segmentos` son filas de `SourceSegment` (o cualquier objeto con `start_s`,
    `end_s`, `text` y opcionalmente `no_speech_prob`).

    Tres pasadas: cada segmento por su cuenta, el consenso por bloques (ver
    `CONSENSO`) y después los momentos. Lo que no alcanza consenso no nombra
    ninguna canción: se queda fuera, que es mejor que un título equivocado.
    """
    crudo: list[tuple] = []
    for seg in segmentos:
        sin_voz = (getattr(seg, "no_speech_prob", None) or 0.0) > SIN_VOZ
        texto = (getattr(seg, "text", "") or "").strip()
        if sin_voz or not texto:
            # El texto de un tramo sin voz es alucinación de Whisper: en Vigo
            # escribió «No me queda» dos veces sobre la guitarra. No identifica.
            crudo.append(("sin_voz", seg, None, None, 0.0))
            continue
        cancion, verso, ratio = identificar(texto, catalogo)
        crudo.append(("voz", seg, cancion, verso, ratio))

    aceptada = _consenso(crudo)

    def vecina(desde: int, paso: int) -> tuple[str | None, float | None]:
        """La canción aceptada más cercana hacia atrás (-1) o adelante (+1)."""
        j = desde + paso
        while 0 <= j < len(crudo):
            if aceptada[j]:
                seg = crudo[j][1]
                return aceptada[j], (seg.end_s if paso < 0 else seg.start_s)
            j += paso
        return None, None

    fuera: list[Momento] = []
    i = 0
    while i < len(crudo):
        clase, seg, cancion, verso, ratio = crudo[i]

        if clase == "sin_voz":
            j = i
            while j + 1 < len(crudo) and crudo[j + 1][0] == "sin_voz":
                j += 1
            inicio, fin = seg.start_s, crudo[j][1].end_s
            duracion = fin - inicio
            if SOLO_MIN_S <= duracion <= SOLO_MAX_S:
                antes, fin_antes = vecina(i, -1)
                despues, ini_despues = vecina(j, +1)
                hereda = (antes if antes and fin_antes is not None
                          and inicio - fin_antes <= HEREDA_MAX_GAP_S else None)
                tipo = "solo"
                motivos = [f"{j - i + 1} tramos seguidos sin voz"]
                if hereda:
                    vuelve = (despues == hereda and ini_despues is not None
                              and ini_despues - fin <= HEREDA_MAX_GAP_S)
                    if not vuelve:
                        # Después no vuelve la canción: es su cierre, no un solo.
                        tipo = "final"
                    motivos.append(f"después de un bloque de «{hereda}»")
                fuera.append(Momento(
                    tipo=tipo, start_s=inicio, end_s=fin, cancion=hereda,
                    confianza=min(1.0, duracion / 30.0), motivos=motivos,
                ))
            elif duracion > SOLO_MAX_S:
                logger.debug("[momentos] %.0fs sin voz: demasiado para ser un solo, "
                             "no se propone", duracion)
            i = j + 1
            continue

        i += 1
        if cancion is None:
            antes, _ = vecina(i - 1, -1)
            despues, _ = vecina(i - 1, +1)
            if antes and antes == despues:
                # Voz que no casa con nada ENTRE dos trozos de la misma canción:
                # es letra mal transcrita («Liga esa hora» en mitad de
                # «Destrozares»), no Robe hablando al público.
                continue
            fuera.append(Momento(
                tipo="habla", start_s=seg.start_s, end_s=seg.end_s,
                confianza=0.5, motivos=["voz que no casa con ninguna letra"],
            ))
            continue

        if aceptada[i - 1] is None:
            logger.debug("[momentos] «%s» casa con «%s» pero sin consenso: no se nombra",
                         seg.text, cancion)
            continue

        if _es(verso, catalogo.estribillos):
            tipo, motivo = "estribillo", "verso que se repite 3+ veces en su canción"
        elif _es(verso, catalogo.arranques):
            tipo, motivo = "arranque", "es de las primeras líneas de la canción"
        else:
            tipo, motivo = "canto", "casa con la letra"
        fuera.append(Momento(
            tipo=tipo, start_s=seg.start_s, end_s=seg.end_s, cancion=cancion,
            verso=verso, confianza=ratio,
            motivos=[motivo, f"{CONSENSO}+ tramos del bloque casan con «{cancion}»"],
        ))
    return fuera
