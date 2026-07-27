"""Tests del auto-arreglo de erratas (botón «Arreglar» de la cola admin).

Blindan el DISPATCHER y las salidas honestas: qué tipos sabe verificar, qué
devuelve cuando no puede, y que un hueco de catálogo (disco sin ingerir) nunca
se cierra en falso. No tocan red: los caminos que consultan fuentes externas
(letras/autoría con consenso) se prueban aparte.
"""
from __future__ import annotations

from app.db.models import ErrataReport, Song
from app.services import errata_fix as ef


class _Result:
    """Doble de un resultado de SQLAlchemy (execute(...).scalar_one_or_none())."""

    def __init__(self, value=None, many=None):
        self._value = value
        self._many = many or []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._many


class _FakeDB:
    """Sesión mínima: `get` por (modelo, id) y `execute` encolado."""

    def __init__(self, objects=None, results=None):
        self._objects = objects or {}
        self._results = list(results or [])
        self.committed = False
        self.rolled_back = False

    def get(self, model, pk):
        return self._objects.get((model.__name__, pk))

    def execute(self, _stmt):
        return self._results.pop(0) if self._results else _Result()

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def flush(self):
        pass


def _errata(**kw) -> ErrataReport:
    base = dict(
        id=1, target_type="catalog", target_id=64, field="original_album",
        reported_wrong="mal", suggested_right="bien", status="needs_human",
    )
    base.update(kw)
    return ErrataReport(**base)


# --- Dispatcher ------------------------------------------------------------- #
def test_errata_ya_resuelta_no_se_vuelve_a_tocar():
    out = ef.try_fix(_FakeDB(), _errata(status="applied"))
    assert out.action == "already_ok"
    assert out.applied is False


def test_tipo_editorial_no_es_verificable():
    """Una errata de texto (interpretación/página) no tiene dato que contrastar:
    se dice claro en vez de fingir un arreglo."""
    out = ef.try_fix(_FakeDB(), _errata(target_type="content"))
    assert out.action == "not_supported"
    assert out.applied is False and out.closed is False


def test_tipos_verificables_tienen_handler():
    assert set(ef._HANDLERS) == {"song_lyrics", "authorship", "catalog", "image"}


def test_excepcion_no_rompe_la_cola():
    def _boom(db, errata):
        raise RuntimeError("fuente caída")

    db = _FakeDB()
    original = ef._HANDLERS["catalog"]
    ef._HANDLERS["catalog"] = _boom
    try:
        out = ef.try_fix(db, _errata())
    finally:
        ef._HANDLERS["catalog"] = original
    assert out.action == "error"
    assert db.rolled_back is True


# --- Parseo de autoría ------------------------------------------------------ #
def test_autor_se_extrae_del_texto_de_la_errata():
    assert ef._author_from_suggestion("Manolo Chinato (autoría)") == "Manolo Chinato"
    assert ef._author_from_suggestion("  Manolo Chinato  ") == "Manolo Chinato"
    assert ef._author_from_suggestion("") == ""


# --- Eje C: hueco de catálogo ---------------------------------------------- #
def _catalog_db(song: Song) -> _FakeDB:
    """BD falsa para el eje catálogo: la canción, su álbum actual y el artista."""
    from app.db.models import Album, Artist

    host = Album(id=7, slug="iros-todos-a-tomar-por-culo", title="Iros todos a tomar por culo",
                 year=1997, kind="live", artist_id=1)
    song.album_id = 7
    return _FakeDB(
        objects={("Song", 64): song, ("Album", 7): host, ("Artist", 1): Artist(id=1, name="Extremoduro", slug="extremoduro")},
        results=[_Result(value=None)],  # el disco original no está en albums
    )


def test_catalogo_sin_disco_no_cierra_si_musicbrainz_no_lo_encuentra(monkeypatch):
    """Caso «Amor castúo»: falta el disco de estudio. Si MusicBrainz no lo da,
    NO se inventa nada: la errata sigue viva y se explica cómo hacerlo a mano."""
    from app.services import catalog_ingest as ci

    monkeypatch.setattr(ci, "find_release_group", lambda *a, **k: None)
    song = Song(id=64, title="Amor castúo (En Directo)",
                original_album_slug="tu-en-tu-casa-nosotros-en-la-hoguera", original_year=1990)
    err = _errata(suggested_right="reingesta el disco de estudio: «Tú en tu casa, nosotros en la hoguera» (1990)")
    out = ef.try_fix(_catalog_db(song), err)
    assert out.action == "not_supported"
    assert out.closed is False and err.status == "needs_human"
    assert "discography.yaml" in (out.detail or "")


def test_catalogo_no_da_de_alta_un_disco_que_no_lleva_la_cancion(monkeypatch):
    """Puerta clave: si la canción de la errata no está en el tracklist, ese no es
    el disco y no se crea nada."""
    from app.services import catalog_ingest as ci

    ev = ci.AlbumEvidence(mbid="x", title="Tú en tu casa, nosotros en la hoguera", year=1990,
                          primary_type="Album", artist_name="Extremoduro", score=100,
                          tracks=[{"position": 1, "title": "Otra cosa", "length_ms": None}])
    monkeypatch.setattr(ci, "find_release_group", lambda *a, **k: ev)
    monkeypatch.setattr(ci, "fetch_tracklist", lambda e: e)
    song = Song(id=64, title="Amor castúo (En Directo)",
                original_album_slug="tu-en-tu-casa-nosotros-en-la-hoguera", original_year=1990)
    err = _errata(suggested_right="reingesta el disco de estudio: «Tú en tu casa, nosotros en la hoguera» (1990)")
    out = ef.try_fix(_catalog_db(song), err)
    assert out.action == "not_supported"
    assert "no es el disco" in out.message
    assert err.status == "needs_human"


def test_catalogo_sin_disco_original_marcado():
    song = Song(id=64, title="Amor castúo (En Directo)", original_album_slug=None)
    db = _FakeDB(objects={("Song", 64): song})
    out = ef.try_fix(db, _errata())
    assert out.action == "not_supported"
    assert "catalog_consensus" in (out.detail or "")


def test_catalogo_con_hueco_tapado_se_cierra():
    """Cuando el disco ya está ingerido con canciones, el botón cierra la errata."""
    from app.db.models import Album

    song = Song(id=64, title="Amor castúo (En Directo)",
                original_album_slug="tu-en-tu-casa-nosotros-en-la-hoguera", original_year=1990)
    album = Album(id=9, slug="tu-en-tu-casa-nosotros-en-la-hoguera",
                  title="Tú en tu casa, nosotros en la hoguera", year=1990, kind="studio")
    db = _FakeDB(
        objects={("Song", 64): song},
        results=[_Result(value=album), _Result(many=[Song(id=200, title="Amor castúo")])],
    )
    err = _errata()
    out = ef.try_fix(db, err)
    assert out.closed is True
    assert err.status == "applied"
    assert db.committed is True


def test_catalogo_con_disco_vacio_no_se_cierra():
    from app.db.models import Album

    song = Song(id=64, title="Amor castúo (En Directo)",
                original_album_slug="tu-en-tu-casa-nosotros-en-la-hoguera")
    album = Album(id=9, slug="tu-en-tu-casa-nosotros-en-la-hoguera",
                  title="Tú en tu casa, nosotros en la hoguera", year=1990, kind="studio")
    db = _FakeDB(objects={("Song", 64): song}, results=[_Result(value=album), _Result(many=[])])
    err = _errata()
    out = ef.try_fix(db, err)
    assert out.closed is False and err.status == "needs_human"
    assert "scripts.ingest" in (out.detail or "")


def test_errata_sin_cancion_no_revienta():
    out = ef.try_fix(_FakeDB(), _errata(target_id=None))
    assert out.action == "not_supported"


# --- Eje A: «ya está arreglado» no puede ser un falso positivo -------------- #
_MALO = "Y llega en tu braguita, el amor, de visita"
_BUENO = "Y lleva en tu braguita el amor de visita"


def _lyrics_errata(**kw) -> ErrataReport:
    return _errata(target_type="song_lyrics", target_id=87, field="lyrics_line",
                   reported_wrong=_MALO, suggested_right=_BUENO, **kw)


def test_no_cierra_como_arreglado_si_el_verso_sigue_mal(monkeypatch):
    """Regresión: comparar el verso contra la letra ENTERA por solapamiento daba
    ≥0.95 entre «llega» y «lleva», así que la errata se cerraba en falso dejando
    el verso malo publicado. Se compara línea a línea por tokens."""
    from app.services import lyric_fetchers

    monkeypatch.setattr(lyric_fetchers, "fetch_all", lambda *a, **k: {})
    song = Song(id=87, album_id=3, title="A Fuego",
                lyrics_clean=f"Yo no sé si te acuerdas\n{_MALO}\nY el resto")
    err = _lyrics_errata()
    out = ef.try_fix(_FakeDB(objects={("Song", 87): song}), err)
    assert out.action != "already_ok"
    assert out.closed is False and err.status == "needs_human"


def test_cierra_cuando_el_verso_bueno_ya_esta_en_la_letra():
    song = Song(id=87, album_id=3, title="A Fuego",
                lyrics_clean=f"Yo no sé si te acuerdas\n{_BUENO}\nY el resto")
    err = _lyrics_errata()
    out = ef.try_fix(_FakeDB(objects={("Song", 87): song}), err)
    assert out.action == "already_ok"
    assert out.closed is True and err.status == "applied"


def test_la_puntuacion_no_impide_reconocer_el_verso_bueno():
    """El mismo verso con comas y sin el «Y» inicial es el mismo verso."""
    song = Song(id=87, album_id=3, title="A Fuego",
                lyrics_clean="Lleva, en tu braguita, el amor de visita.")
    out = ef.try_fix(_FakeDB(objects={("Song", 87): song}), _lyrics_errata())
    assert out.action == "already_ok"
