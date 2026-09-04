"""¿Este vídeo de YouTube habla del universo Robe / Extremoduro?

Los canales con `relevance: catalog` en `data/sources.yaml` NO son monotemáticos:
@tesonica sube análisis de La Ley Innata, pero también de SOAD, Apocalyptica o
ergonomía del violonchelo. Solo hay que encolar lo primero.

El criterio es el que pidió el usuario: que el TÍTULO (y opcionalmente la
descripción) mencione Robe, Extremoduro, o el nombre de una canción o disco del
catálogo. El vocabulario NO se escribe a mano: se deriva de la BD (`Song.title`,
`Album.title`), así que cuando entra un disco nuevo el filtro lo reconoce solo.

Los títulos se parten en dos grupos por una razón medida: hay canciones cuyo
título normalizado es una palabra corriente y corta («Mama», «Golfa», «Enemigo»,
«Guerrero», «La Carrera» → «carrera»…). Buscarlas por substring convertiría
cualquier vídeo de metal en material de Extremoduro, así que esas solo casan como
PALABRA COMPLETA, solo en el TÍTULO —nunca en la descripción, que es prosa larga
donde una palabra común aparece por casualidad— y se etiquetan como señal débil
para que se vean como tal en el email de aprobación.

Ese último detalle no es teórico: medido contra el canal, buscar títulos cortos en
la descripción metía «Llegó el turno de Tarja» porque hablaba de «su carrera».

Devuelve siempre los MOTIVOS del match: sin ellos no hay forma de auditar por
qué un vídeo acabó en la cola.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

# Reutilizamos la normalización del fact-check (minúsculas sin acentos, comillas
# normalizadas, artículo inicial fuera). Una sola fuente de verdad: si allí
# cambia cómo se casan los títulos, aquí cambia igual.
from app.services.fact_check import _norm as norm_title

# Términos que por sí solos acreditan el tema.
BASE_TERMS: tuple[str, ...] = ("robe", "extremoduro", "roberto iniesta")

# Umbral (en caracteres normalizados) desde el cual un título del catálogo es lo
# bastante distintivo para buscarlo como substring. 10 y no 12 porque «La ley
# innata» normaliza a «ley innata» (10) y es todo lo distintiva que se puede pedir;
# por debajo caen las palabras sueltas corrientes, que es lo que hay que contener.
MIN_DISTINCTIVE = 10

# La descripción se mira solo por arriba: más abajo son hashtags, links de
# Patreon y firmas que repiten el nombre del canal.
DESCRIPTION_CHARS = 600


@dataclass
class RelevanceVocab:
    """Vocabulario derivado de la BD. Construir una vez por pasada, no por vídeo."""

    distinctive: dict[str, str] = field(default_factory=dict)  # norm -> display
    short: dict[str, str] = field(default_factory=dict)        # norm -> display

    def __len__(self) -> int:  # para logs
        return len(self.distinctive) + len(self.short)


def build_vocab(db: Session) -> RelevanceVocab:
    """Títulos de canciones y discos del catálogo, repartidos por longitud."""
    from app.db.models import Album, Song

    vocab = RelevanceVocab()
    titles = [t for (t,) in db.query(Song.title).all() if t]
    titles += [t for (t,) in db.query(Album.title).all() if t]
    for raw in titles:
        n = norm_title(raw)
        if not n:
            continue
        bucket = vocab.distinctive if len(n) >= MIN_DISTINCTIVE else vocab.short
        bucket.setdefault(n, raw)
    return vocab


def _word_in(needle: str, haystack: str) -> bool:
    """`needle` aparece en `haystack` como palabra completa."""
    return re.search(rf"(?<![a-z0-9ñ]){re.escape(needle)}(?![a-z0-9ñ])", haystack) is not None


def _hits(
    text: str, vocab: RelevanceVocab, *, where: str, allow_short: bool = True
) -> list[str]:
    """Motivos de match dentro de un texto ya normalizado."""
    if not text:
        return []
    out: list[str] = []
    for term in BASE_TERMS:
        if _word_in(term, text):
            out.append(f"{where}: «{term}»")
    for n, display in vocab.distinctive.items():
        if n in text:
            out.append(f"{where}: título «{display}»")
    if allow_short:
        for n, display in vocab.short.items():
            if _word_in(n, text):
                out.append(f"{where}: título corto «{display}» (señal débil)")
    return out


def is_relevant(
    title: str | None,
    description: str | None = None,
    *,
    vocab: RelevanceVocab,
    use_description: bool = False,
) -> tuple[bool, list[str]]:
    """¿El vídeo trata del universo Robe/Extremoduro? → (sí/no, motivos).

    El título manda. La descripción solo se consulta si el canal la habilita y el
    título no ha dado nada: rescata piezas con título críptico cuya descripción
    sí dice de qué van (medido: 10 vídeos de @tesonica, entre ellos los dos
    capítulos de «Pedrá: ¿por qué ese nombre?»).
    """
    reasons = _hits(norm_title(title or ""), vocab, where="título")
    if reasons:
        return True, reasons
    if use_description and description:
        reasons = _hits(
            norm_title(description[:DESCRIPTION_CHARS]),
            vocab,
            where="descripción",
            allow_short=False,  # ver docstring del módulo: «su carrera» ≠ «La Carrera»
        )
        if reasons:
            return True, reasons
    return False, []
