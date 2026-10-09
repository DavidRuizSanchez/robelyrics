"""El verso es de SU canción, y una canción es su versión original (09-10-2026).

Publicado en Instagram ese día, y medido en prod:
  - un clip de «Si te vas...» cerraba con un verso de «Bri, bri, bli, bli»
    (153 de 192 posts con verso usaban uno de solo tres comodines);
  - un post sobre «De Acero (En Directo)» la situaba en «Iros todos a tomar por
    culo (1992)» —el directo es de 1997— y su verso era «Deltoya» ×35.
"""
from __future__ import annotations

import pytest
from sqlalchemy import JSON, MetaData, Text, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Session

from app.db.models import Album, Artist, Line, Song
from app.services import versiones
from app.services.fact_check import pares_disco_anio_falsos
from app.services.instagram import robe_quote


@pytest.fixture()
def db():
    md = MetaData()
    for modelo in (Artist, Album, Song, Line):
        t = modelo.__table__.to_metadata(md)
        for col in t.columns:
            if isinstance(col.type, (JSONB, ARRAY)):
                col.type = JSON()
            elif isinstance(col.type, TSVECTOR):
                col.type = Text()
            sd = col.server_default
            if sd is not None and "::" in str(getattr(sd, "arg", "")):
                col.server_default = None
        t.indexes.clear()
    engine = create_engine("sqlite://")
    md.create_all(engine)
    with Session(engine) as s:
        art = Artist(id=1, slug="extremoduro", name="Extremoduro")
        deltoya = Album(id=1, artist_id=1, slug="deltoya", title="Deltoya", year=1992, kind="studio")
        iros = Album(id=2, artist_id=1, slug="iros-todos-a-tomar-por-culo",
                     title="Iros todos a tomar por culo", year=1997, kind="live")
        material = Album(id=3, artist_id=1, slug="material-defectuoso",
                         title="Material defectuoso", year=2011, kind="studio")
        s.add_all([art, deltoya, iros, material])
        s.flush()
        _cancion(s, 29, "De Acero", "de-acero", 1, [
            "Aunque me vaya de acero", "por dentro llevo la herida abierta,",
            "y nadie la ve.", "Que te den, que te den,", "que me voy a mi manera.",
            "Que te den, que te den,", "relleno uno", "relleno dos",
            "Que te den, que te den,",
        ])
        _cancion(s, 66, "De Acero (En Directo)", "de-acero-en-directo", 2,
                 ["Aunque me vaya de acero"])
        _cancion(s, 34, "Deltoya", "deltoya", 1, [
            "Deltoya, deltoya, deltoya, deltoya, deltoya",
            "Deltoya, deltoya, deltoya, deltoya, deltoya",
            "Deltoya, deltoya, deltoya, deltoya, delto'",
            "Y me fui con ella al otro lado del río.",
        ])
        _cancion(s, 80, "Si te vas...", "si-te-vas", 3, [
            "Toma primera, eh",
            "Si te vas, me quedo en esta calle sin salida,",
            "buscando una salida que no existe.",
        ])
        s.commit()
        yield s


def _cancion(s, sid, titulo, slug, album_id, versos):
    s.add(Song(id=sid, title=titulo, slug=slug, album_id=album_id))
    s.flush()
    for i, v in enumerate(versos):
        s.add(Line(song_id=sid, line_index=i, text=v))


# --- Directos → original ---------------------------------------------------- #
def test_un_directo_lleva_a_su_original_de_estudio(db):
    directo = db.get(Song, 66)
    assert not versiones.es_original(directo, directo.album)
    orig = versiones.version_original(db, directo)
    assert orig.id == 29 and orig.album.title == "Deltoya" and orig.album.year == 1992


def test_un_original_es_el_mismo(db):
    s = db.get(Song, 29)
    assert versiones.version_original(db, s) is s


# --- El verso: de su canción o ninguno -------------------------------------- #
def test_el_verso_es_de_la_cancion_y_se_cita_con_barras(db):
    v = robe_quote.verso_de_cancion(db, 80)
    assert v["song"] == "Si te vas..." and v["song_id"] == 80
    assert " / " in v["line"] and "calle sin salida" in v["line"]


def test_la_charla_de_la_grabacion_no_es_un_verso(db):
    assert "Toma primera" not in robe_quote.verso_de_cancion(db, 80)["line"]


def test_el_titulo_repetido_no_es_un_verso(db):
    v = robe_quote.verso_de_cancion(db, 34)
    assert "deltoya, deltoya" not in v.get("line", "").lower()
    assert v["line"].startswith("Y me fui con ella")


def test_el_verso_de_un_directo_sale_de_su_original(db):
    v = robe_quote.verso_de_cancion(db, 66)
    assert v["song_id"] == 29 and v["year"] == 1992 and v["song"] == "De Acero"


def test_prefiere_el_estribillo(db):
    assert robe_quote.verso_de_cancion(db, 29)["line"].startswith("Que te den")


def test_sin_cancion_no_hay_verso(db):
    assert robe_quote.verso_de_cancion(db, None) == {}


def test_un_clip_dice_su_cancion_y_su_verso(db):
    from app.db.models import InstagramQueueItem

    item = InstagramQueueItem(
        media_type="CLIP", content_type="clip", title="x",
        summary="Tramo 640-658s\nCanción: Si te vas...\nVerso (de nuestra letra): "
                "Si te vas, me quedo en esta calle sin salida,",
    )
    assert robe_quote.cancion_del_post(db, item) == (
        80, "Si te vas, me quedo en esta calle sin salida,")


def test_una_noticia_no_tiene_cancion(db):
    from app.db.models import InstagramQueueItem

    item = InstagramQueueItem(media_type="CAROUSEL", content_type="news", title="x",
                              summary="Un tributo canta De Acero y Deltoya en Cuenca")
    assert robe_quote.cancion_del_post(db, item) == (None, None)


# --- «Disco» (AAAA) ----------------------------------------------------------- #
def test_un_disco_con_el_anio_de_otro_bloquea(db):
    texto = "formó parte del álbum 'Iros todos a tomar por culo' (1992), refleja"
    assert pares_disco_anio_falsos(db, texto) == [
        "«Iros todos a tomar por culo» (1992): el disco es de 1997"]


def test_disco_y_cancion_homonimos_no_dan_falso(db):
    assert pares_disco_anio_falsos(db, "— Extremoduro, «Deltoya» (1992)") == []
    assert pares_disco_anio_falsos(db, "el directo «Iros todos a tomar por culo» (1997)") == []
