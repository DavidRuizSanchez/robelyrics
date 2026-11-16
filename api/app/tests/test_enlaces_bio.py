"""`/enlaces`: cada post de Instagram lleva a la página de la que habla (16-11-2026).

Solo sale lo que tiene destino propio y publicado. Un clip sin canción no se
enlaza por su título: el #504 decía «La Carrera» y sonaba «Destrozares».
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.db.models import (
    Album,
    Artist,
    InstagramQueueItem,
    InstagramQueueMedia,
    Line,
    Person,
    Post,
    SeoContent,
    Song,
    VideoClip,
)
from app.services import enlaces_bio
from app.tests.test_admin_summary import _con_dependencias


@pytest.fixture()
def db():
    from sqlalchemy import ARRAY, JSON, MetaData, Text, create_engine
    from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
    from sqlalchemy.orm import Session

    md = MetaData()
    modelos = (Artist, Album, Song, Line, Person, Post, SeoContent, InstagramQueueItem,
               InstagramQueueMedia, VideoClip)
    for tabla in _con_dependencias([m.__table__ for m in modelos]):
        t = tabla.to_metadata(md)
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
        yield s


def _ficha(db, tipo, ident, slug, *, publicada=True):
    db.add(SeoContent(entity_type=tipo, entity_id=ident, slug=slug, body_md="x",
                      published=publicada, entities=[], secondary_keywords=[], outline=[]))


T0 = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


def _item(db, n, tipo, clave=None, *, titulo="Un post", blog_post_id=None,
          status="published", imagen=None):
    it = InstagramQueueItem(
        day=date(2026, 11, 16), content_type=tipo, content_key=clave, title=titulo,
        blog_post_id=blog_post_id, status=status,
        published_at=T0 - timedelta(hours=n) if status == "published" else None,
    )
    db.add(it)
    db.flush()
    if imagen:
        db.add(InstagramQueueMedia(item_id=it.id, position=0, kind="image", url=imagen))
    return it


@pytest.fixture()
def catalogo(db):
    art = Artist(slug="extremoduro", name="Extremoduro")
    db.add(art)
    db.flush()
    alb = Album(slug="agila", title="Agila", year=1996, artist_id=art.id)
    borrador = Album(slug="iros-todos", title="Iros todos a tomar por culo", year=1997,
                     artist_id=art.id)
    db.add_all([alb, borrador])
    db.flush()
    song = Song(slug="so-payaso", title="So payaso", album_id=alb.id)
    db.add(song)
    db.flush()
    linea = Line(song_id=song.id, line_index=0, text="Me paso el día bostezando")
    db.add(linea)
    persona = Person(slug="manolo-chinato", full_name="Manolo Chinato")
    db.add(persona)
    post = Post(slug="flores-amarillas-2027", kind="news", status="published",
                title="Flores Amarillas 2027", body_md="x")
    db.add(post)
    db.flush()
    _ficha(db, "album", alb.id, "agila")
    _ficha(db, "album", borrador.id, "iros-todos", publicada=False)
    _ficha(db, "song", song.id, "so-payaso")
    _ficha(db, "person", persona.id, "manolo-chinato")
    db.flush()
    return {"song": song, "linea": linea, "post": post}


def test_cada_tipo_lleva_a_su_pagina(db, catalogo):
    _item(db, 1, "quote", f"quote:line_{catalogo['linea'].id}", titulo="Me paso el día")
    _item(db, 2, "news", None, blog_post_id=catalogo["post"].id)
    _item(db, 3, "ephemeris", "ephemeris:album_agila_2026")
    _item(db, 4, "ephemeris", "ephemeris:birth_manolo-chinato_2026")
    _item(db, 5, "product", "product:como-lo-diria-robe:abc")
    db.flush()

    destinos = [(e.tipo, e.destino) for e in enlaces_bio.ultimos(db)]
    assert destinos == [
        ("song", "/extremoduro/agila/so-payaso"),
        ("post", "/blog/flores-amarillas-2027"),
        ("album", "/extremoduro/agila"),
        ("person", "/personas/manolo-chinato"),
        ("registro", "/registro"),
    ]


def test_lo_que_no_tiene_pagina_propia_no_sale(db, catalogo):
    _item(db, 1, "news", None)                                  # noticia ajena sin artículo
    _item(db, 2, "anecdote", "anecdote:agila-castuo")
    _item(db, 3, "ephemeris", "ephemeris:album_iros-todos_2026")  # ficha en borrador
    _item(db, 4, "ephemeris", "ephemeris:birth_nadie_2026")       # persona inexistente
    _item(db, 5, "quote", f"quote:line_{catalogo['linea'].id}", status="pending")
    borrador = Post(slug="borrador", kind="news", status="pending_review", title="B",
                    body_md="x")
    db.add(borrador)
    db.flush()
    _item(db, 6, "news", None, blog_post_id=borrador.id)
    db.flush()

    assert enlaces_bio.ultimos(db) == []


def test_un_clip_solo_se_enlaza_con_su_cancion_guardada(db, catalogo):
    sin = _item(db, 1, "clip", "clip:abc:0-30", titulo="El solo de «So payaso» — Vigo")
    con = _item(db, 2, "clip", "clip:def:0-30", titulo="Arranca «So payaso» — Murcia")
    db.add_all([
        VideoClip(video_id="abc", url="https://youtu.be/abc", end_s=30, queue_item_id=sin.id),
        VideoClip(video_id="def", url="https://youtu.be/def", end_s=30, queue_item_id=con.id,
                  song_id=catalogo["song"].id),
    ])
    db.flush()

    enlaces = enlaces_bio.ultimos(db)
    assert [(e.id, e.destino) for e in enlaces] == [(con.id, "/extremoduro/agila/so-payaso")]
    # La raya larga de la procedencia no se pinta en la web.
    assert enlaces[0].titulo == "Arranca «So payaso» · Murcia"


def test_limite_y_orden(db, catalogo):
    for n in range(5):
        _item(db, n, "product", f"product:x:{n}")
    db.flush()
    assert len(enlaces_bio.ultimos(db, limite=3)) == 3


def test_miniatura_cuadrada_de_cloudinary():
    base = "https://res.cloudinary.com/ddnkzrplj/image/upload/v1/entreinteriores-ig/a.jpg"
    assert enlaces_bio.miniatura(base) == (
        "https://res.cloudinary.com/ddnkzrplj/image/upload/"
        "c_fill,g_auto,w_480,h_480,f_auto,q_auto/v1/entreinteriores-ig/a.jpg"
    )
    video = "https://res.cloudinary.com/ddnkzrplj/video/upload/v1/clips/b.mp4"
    assert enlaces_bio.miniatura(video) == (
        "https://res.cloudinary.com/ddnkzrplj/video/upload/"
        "so_1,c_fill,g_auto,w_480,h_480,f_auto,q_auto/v1/clips/b.jpg"
    )
    assert enlaces_bio.miniatura("https://otra.web/x.jpg") == "https://otra.web/x.jpg"
    assert enlaces_bio.miniatura(None) is None


def test_la_imagen_es_la_primera_del_post(db, catalogo):
    url = "https://res.cloudinary.com/ddnkzrplj/image/upload/v1/entreinteriores-ig/p.jpg"
    _item(db, 1, "product", "product:x:1", imagen=url)
    db.flush()
    [enlace] = enlaces_bio.ultimos(db)
    assert enlace.imagen.endswith("/c_fill,g_auto,w_480,h_480,f_auto,q_auto/v1/entreinteriores-ig/p.jpg")
