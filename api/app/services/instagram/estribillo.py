"""¿Dónde se canta el estribillo en este vídeo? Y de paso: ¿es esta canción?

Criterio de David (09-10-2026): un clip es UNA canción, cortado en el estribillo,
y el texto del post es el de esa canción. No hace falta transcribir conciertos
enteros: el vídeo ya es de una sola canción (su título la nombra), así que basta
con escuchar sus primeros minutos y buscar el estribillo de NUESTRA letra.

Localizar y verificar es el MISMO paso, y por eso no hay clip «aproximado»: o
se oye el estribillo de esa canción, o no hay clip.

Dos listones, medidos en el pipeline de conciertos:
  - un fragmento corto casa con cualquier cosa («¡Vamos Manolo!» salió como
    verso a 0,80), así que los tramos de menos de 4 palabras no cuentan;
  - un solo tramo que case puede ser casualidad: para dar por buena la CANCIÓN
    se piden al menos 3 tramos de voz DISTINTOS que casen con su letra. Distintos
    porque sobre música Whisper entra en bucle (medido el 09-10-2026: repitió las
    mismas cuatro frases cada 25 s y luego «Subtítulos realizados por la
    comunidad de Amara.org»), y una frase repetida no prueba nada.

Puro (sin BD ni red): recibe los segmentos de Whisper y la letra.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.lyric_guard import best_ratio, normalize

MIN_PALABRAS = 4
UMBRAL = 0.75
MIN_TRAMOS_CANCION = 3
SIN_VOZ = 0.6
MIN_CLIP_S = 12.0
MAX_CLIP_S = 30.0
MARGEN_S = 1.5


@dataclass
class Tramo:
    start_s: float
    end_s: float
    verso: str            # el de NUESTRA letra, no lo que transcribió Whisper
    tramos_cancion: int   # cuántos segmentos casan con la letra (la evidencia)


def _voz(seg: dict) -> str | None:
    if (seg.get("no_speech_prob") or 0) > SIN_VOZ:
        return None
    texto = normalize(seg.get("text") or "")
    return texto if len(texto.split()) >= MIN_PALABRAS else None


def localizar(segmentos: list[dict], estribillo: list[str], letra: list[str]) -> Tramo | None:
    """El tramo del primer estribillo, o None si no se oye ESTA canción o no se
    oye su estribillo. `segmentos` = [{start_s|start, end_s|end, text,
    no_speech_prob}] de Whisper; `estribillo` y `letra`, líneas de la BD."""
    letra_norm = normalize(" ".join(letra))
    coro = [(v, normalize(v)) for v in estribillo if normalize(v)]
    if not letra_norm or not coro:
        return None

    def _ini(s):
        return float(s.get("start_s", s.get("start", 0.0)))

    def _fin(s):
        return float(s.get("end_s", s.get("end", 0.0)))

    casan: set[str] = set()
    marcados: list[tuple[dict, str | None]] = []
    for seg in segmentos:
        voz = _voz(seg)
        if voz is None:
            marcados.append((seg, None))
            continue
        if best_ratio(voz, letra_norm) >= UMBRAL:
            casan.add(voz)
        verso = next((v for v, vn in coro if best_ratio(voz, vn) >= UMBRAL
                      or best_ratio(vn, voz) >= UMBRAL), None)
        marcados.append((seg, verso))

    casan_letra = len(casan)
    if casan_letra < MIN_TRAMOS_CANCION:
        return None
    primero = next((i for i, (_, v) in enumerate(marcados) if v), None)
    if primero is None:
        return None

    inicio = max(0.0, _ini(marcados[primero][0]) - MARGEN_S)
    fin = _fin(marcados[primero][0])
    # El bloque: estribillo seguido (los tramos sin voz en medio no lo cortan).
    for seg, verso in marcados[primero + 1:]:
        if verso is None and _voz(seg) is not None:
            break
        if _fin(seg) - inicio > MAX_CLIP_S:
            break
        fin = _fin(seg)
    fin = max(fin, inicio + MIN_CLIP_S)
    fin = min(fin, inicio + MAX_CLIP_S)
    return Tramo(start_s=round(inicio, 2), end_s=round(fin, 2),
                 verso=marcados[primero][1] or "", tramos_cancion=casan_letra)
