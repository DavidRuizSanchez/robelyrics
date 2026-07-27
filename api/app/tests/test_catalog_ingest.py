"""Tests del alta verificada de discos ausentes (Eje C de punta a punta).

Blindan las dos cosas que pueden meter datos falsos en el site:
  - Las SEIS puertas de `certify`: basta que falle una para no crear nada.
  - `link_original_versions`: a quién se le marca el disco original. Aquí se coló
    un fallo real en pruebas (marcó canciones de un disco ANTERIOR como si su
    primera aparición fuese posterior, y casó «Extremaydura» con «Villancico del
    Rey de Extremadura» por usar solapamiento en vez de igualdad de título).

Sin red: la evidencia de MusicBrainz se construye a mano.
"""
from __future__ import annotations

import pytest

from app.db.models import Album, Song
from app.services import catalog_ingest as ci

_TRACKS = [
    {"position": 1, "title": "La hoguera", "length_ms": 272000},
    {"position": 2, "title": "Extremaydura", "length_ms": 209000},
    {"position": 3, "title": "Amor castúo", "length_ms": 261000},
]


def _ev(**kw) -> ci.AlbumEvidence:
    base = dict(
        mbid="be718ce7", title="Tú en tu casa, nosotros en la hoguera", year=1990,
        primary_type="Album", artist_name="Extremoduro", score=100, tracks=list(_TRACKS),
    )
    base.update(kw)
    return ci.AlbumEvidence(**base)


def _certify(ev, **over):
    kwargs = dict(
        expected_title="Tú en tu casa, nosotros en la hoguera",
        expected_artist="Extremoduro",
        expected_year=1990,
        must_contain="Amor castúo",
    )
    kwargs.update(over)
    return ci.certify(ev, **kwargs)


# --- Las seis puertas ------------------------------------------------------- #
def test_certifica_cuando_todo_encaja():
    assert _certify(_ev()).mbid == "be718ce7"


def test_sin_evidencia_no_hay_alta():
    with pytest.raises(ci.AlbumNotCertain, match="no encuentra"):
        _certify(None)


def test_score_flojo_no_basta():
    with pytest.raises(ci.AlbumNotCertain, match="floja"):
        _certify(_ev(score=55))


def test_titulo_distinto_se_rechaza():
    with pytest.raises(ci.AlbumNotCertain):
        _certify(_ev(title="Rock Transgresivo"))


def test_artista_distinto_se_rechaza():
    with pytest.raises(ci.AlbumNotCertain, match="no de"):
        _certify(_ev(artist_name="Rosendo"))


def test_discrepancia_de_ano_manda_a_revision():
    """Dos fuentes con años distintos = duda: se para y lo mira un humano."""
    with pytest.raises(ci.AlbumNotCertain, match="Discrepancia de año"):
        _certify(_ev(year=1994))


def test_sin_tracklist_no_se_inventan_canciones():
    with pytest.raises(ci.AlbumNotCertain, match="no me invento"):
        _certify(_ev(tracks=[]))


def test_cancion_ausente_del_tracklist_no_es_el_disco():
    with pytest.raises(ci.AlbumNotCertain, match="no es el disco"):
        _certify(_ev(), must_contain="Standby")


# --- Título desnudo --------------------------------------------------------- #
def test_bare_title_quita_el_sufijo_de_version():
    assert ci.bare_title("La Hoguera (Rock Transgresivo)") == "la hoguera"
    assert ci.bare_title("Amor castúo (En Directo)") == "amor castuo"
    assert ci.bare_title("Arrebato") == "arrebato"


# --- Enlazado de versiones -------------------------------------------------- #
class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def __iter__(self):
        return iter(self._rows)


class _DB:
    """Devuelve primero las canciones del disco nuevo y luego los pares (Song, Album)."""

    def __init__(self, own, others):
        self._queue = [_Rows(own), _Rows(others)]

    def execute(self, _stmt):
        return self._queue.pop(0)


def _album(**kw) -> Album:
    base = dict(id=32, slug="tu-en-tu-casa-nosotros-en-la-hoguera",
                title="Tú en tu casa, nosotros en la hoguera", year=1990, kind="studio", artist_id=1)
    base.update(kw)
    return Album(**base)


def test_enlaza_las_versiones_posteriores():
    nuevo = _album()
    own = [Song(id=200, title="La hoguera"), Song(id=201, title="Amor castúo")]
    live = Album(id=7, slug="iros-todos", title="Iros todos", year=1997, kind="live", artist_id=1)
    others = [
        (Song(id=64, title="Amor castúo (En Directo)"), live),
        (Song(id=68, title="La Hoguera (En Directo)"), live),
    ]
    n = ci.link_original_versions(_DB(own, others), nuevo, artist_id=1)
    assert n == 2
    assert others[0][0].original_album_slug == "tu-en-tu-casa-nosotros-en-la-hoguera"
    assert others[0][0].original_year == 1990


def test_no_toca_canciones_de_un_disco_anterior():
    """Bug real: marcó 7 canciones de Rock Transgresivo (1989) como si su primera
    aparición fuese un disco de 1990. Un disco posterior nunca es el original."""
    nuevo = _album()
    own = [Song(id=200, title="La hoguera"), Song(id=201, title="Extremaydura")]
    previo = Album(id=1, slug="rock-transgresivo", title="Rock Transgresivo",
                   year=1989, kind="studio", artist_id=1)
    others = [
        (Song(id=15, title="La Hoguera (Rock Transgresivo)"), previo),
        (Song(id=8, title="Extremaydura (Rock Transgresivo)"), previo),
    ]
    assert ci.link_original_versions(_DB(own, others), nuevo, artist_id=1) == 0
    assert others[0][0].original_album_slug is None


def test_no_casa_un_titulo_que_solo_contiene_al_otro():
    """Bug real: «Extremaydura» casaba dentro de «Villancico del Rey de
    Extremadura» al comparar por solapamiento en vez de por igualdad."""
    nuevo = _album()
    own = [Song(id=201, title="Extremaydura")]
    otro = Album(id=8, slug="canciones-prohibidas", title="Canciones prohibidas",
                 year=1998, kind="studio", artist_id=1)
    others = [(Song(id=86, title="Villancico del Rey de Extremadura (Vaya Puta Mierda)"), otro)]
    assert ci.link_original_versions(_DB(own, others), nuevo, artist_id=1) == 0
    assert others[0][0].original_album_slug is None


def test_snippet_yaml_para_versionar_el_alta():
    out = ci.yaml_snippet(_ev(release_date="1990-02-02"), "tu-en-tu-casa-nosotros-en-la-hoguera")
    assert "slug: tu-en-tu-casa-nosotros-en-la-hoguera" in out
    assert "year: 1990" in out
    assert "release_date: 1990-02-02" in out
