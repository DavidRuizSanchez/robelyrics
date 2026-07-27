"""Tests del relleno de fichas SEO ausentes.

Lo que blindan: que un disco dado de alta automáticamente no deje páginas
enlazadas respondiendo 404. La ficha del ÁLBUM es la prioritaria (es la que
enlaza el listado de discografía), así que un tope por pasada no puede dejarla
fuera para gastarse el cupo en canciones.
"""
from __future__ import annotations

from app.db.models import Album, Song
from scripts.seo import fill_missing_content as fmc


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _DB:
    def __init__(self, queue):
        self._queue = list(queue)

    def execute(self, _stmt):
        return _Rows(self._queue.pop(0))


_ALBUM = Album(id=32, slug="tu-en-tu-casa-nosotros-en-la-hoguera", title="Tú en tu casa",
               year=1990, kind="studio", artist_id=1)
_SONGS = [Song(id=200 + i, album_id=32, title=f"C{i}", slug=f"c{i}") for i in range(3)]


def test_album_recien_creado_necesita_su_ficha_y_las_de_sus_canciones():
    # execute(): álbum → albums cubiertos → songs cubiertas → canciones del álbum
    db = _DB([[_ALBUM], [], [], _SONGS])
    pend = fmc.missing_for_album(db, _ALBUM.slug)
    assert pend["album"] == [_ALBUM.slug]
    assert pend["song"] == ["c0", "c1", "c2"]


def test_no_regenera_lo_que_ya_tiene_ficha():
    db = _DB([[_ALBUM], [32], [200, 201, 202], _SONGS])
    assert fmc.missing_for_album(db, _ALBUM.slug) == {}


def test_album_sin_ficha_pero_canciones_hechas():
    db = _DB([[_ALBUM], [], [200, 201, 202], _SONGS])
    pend = fmc.missing_for_album(db, _ALBUM.slug)
    assert pend == {"album": [_ALBUM.slug]}


def test_album_inexistente_no_revienta():
    assert fmc.missing_for_album(_DB([[]]), "no-existe") == {}


def test_el_tope_prioriza_la_ficha_del_album():
    """El listado de discografía enlaza el álbum: su ficha va primero, siempre."""
    # execute(): albums cubiertos → albums → songs cubiertas → songs
    pend = fmc.missing_everywhere(_DB([[], [_ALBUM], [], _SONGS]), limit=2)
    assert pend["album"] == [_ALBUM.slug]
    assert len(pend.get("song", [])) == 1


def test_sin_tope_devuelve_todo():
    pend = fmc.missing_everywhere(_DB([[], [_ALBUM], [], _SONGS]))
    assert len(pend["album"]) == 1 and len(pend["song"]) == 3
