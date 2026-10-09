"""Una canción es su versión ORIGINAL. Un directo es una grabación de ella.

El 09-10-2026 se publicó un post (blog e Instagram) sobre «De Acero (En
Directo)» que situaba la canción en «Iros todos a tomar por culo (1992)»: el
directo es de 1997 y «De Acero» es de «Deltoya» (1992). Las 14 filas `Song` del
«Iros…» vienen de la ingesta de Genius, anterior a `album_tracks`, y los
selectores de contenido las trataban como canciones propias.

Este módulo es la ÚNICA respuesta a dos preguntas, para que no diverjan:
  - ¿esta fila es una grabación no original (directo, recopilatorio)?
  - ¿cuál es su versión original de estudio?

Lo que se escribe sobre una canción habla de su original: su disco, su año, su
letra. Que exista una versión en directo es un dato más, nunca el contexto.
"""
from __future__ import annotations

import re

from sqlalchemy import select, true
from sqlalchemy.orm import Session

from app.db.models import Album, Song
from app.services.url_resolver import is_live_version

# Tipos de disco que NO son la primera publicación de sus canciones. Un EP o un
# disco de estudio sí lo son (el EP «Somos unos animales» es material original).
KINDS_NO_ORIGINALES = ("live", "compilation", "single")

_SUFIJO_DIRECTO = re.compile(r"\s*[\(\[]\s*en directo\s*[\)\]]\s*$", re.IGNORECASE)
_PARENTESIS_FINAL = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]\s*$")


def es_original(song: Song, album: Album | None) -> bool:
    """¿La fila es la versión original (estudio o EP), no un directo?"""
    if is_live_version(song.slug or "", song.title or ""):
        return False
    return not (album is not None and (album.kind or "studio") in KINDS_NO_ORIGINALES)


def _clave(titulo: str) -> str:
    from app.services.lyric_guard import normalize

    return normalize(_SUFIJO_DIRECTO.sub("", titulo or ""))


def _clave_base(titulo: str) -> str:
    """Sin ningún paréntesis final: «Pepe Botika (¿Dónde están mis amigos?)» →
    «pepe botika». Solo se usa si la clave completa no casa."""
    from app.services.lyric_guard import normalize

    t = _SUFIJO_DIRECTO.sub("", titulo or "")
    return normalize(_PARENTESIS_FINAL.sub("", t) or t)


def candidatos_originales(db: Session, song: Song) -> list[tuple[Song, Album]]:
    """Filas originales del MISMO artista cuyo título casa con el de `song`,
    del disco más antiguo al más reciente. Vacío si no hay ninguna."""
    album = db.get(Album, song.album_id) if song.album_id else None
    filas = db.execute(
        select(Song, Album).join(Album, Song.album_id == Album.id)
        .where(Song.id != song.id)
        .where(Album.artist_id == album.artist_id if album else true())
    ).all()
    originales = [(s, a) for s, a in filas if es_original(s, a)]
    for clave in (_clave, _clave_base):
        objetivo = clave(song.title)
        hit = [(s, a) for s, a in originales if clave(s.title) == objetivo]
        if hit:
            return sorted(hit, key=lambda sa: (sa[1].year or 9999, sa[0].id))
    return []


def version_original(db: Session, song: Song) -> Song:
    """La versión de la que se debe hablar. Si `song` ya es original, ella
    misma. Si es un directo:
      1. la fijada en `original_album_slug` (la verdad curada manda);
      2. si no, la de estudio más antigua con el mismo título;
      3. si no hay ninguna, la propia fila (y quien la use debe saber que es un
         directo: `es_original` sigue diciendo False).
    """
    album = db.get(Album, song.album_id) if song.album_id else None
    if es_original(song, album):
        return song
    cands = candidatos_originales(db, song)
    if song.original_album_slug:
        fijada = [s for s, a in cands if a.slug == song.original_album_slug]
        if fijada:
            return fijada[0]
    return cands[0][0] if cands else song
