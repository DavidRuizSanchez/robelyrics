"""Fechas de subida de los vídeos: con hora y zona, o no valen (GSC, 20-11-2026)."""
from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import httpx

from app.routers.public import fecha_de_subida
from app.services import video_dates as vd


def test_solo_vale_el_iso_con_hora_y_zona():
    assert vd.tiene_hora_y_zona("2018-11-15T17:00:04Z")
    assert vd.tiene_hora_y_zona("2018-11-15T17:00:04+00:00")
    assert vd.tiene_hora_y_zona("2018-11-15T17:00:04.123+0200")
    assert not vd.tiene_hora_y_zona("2018-11-15")            # lo que se servía
    assert not vd.tiene_hora_y_zona("2018-11-15T17:00:04")   # sin zona
    assert not vd.tiene_hora_y_zona(None)


def test_parse_subida_no_inventa_la_hora():
    assert vd.parse_subida("2018-11-15") == (date(2018, 11, 15), None)
    dia, instante = vd.parse_subida("2018-11-15T23:30:00Z")
    assert dia == date(2018, 11, 15)
    assert instante == datetime(2018, 11, 15, 23, 30, tzinfo=UTC)
    assert vd.parse_subida("ayer") == (None, None)
    assert vd.parse_subida(None) == (None, None)


def test_la_api_sirve_la_fecha_completa_si_la_hay():
    con_hora = SimpleNamespace(published_at=datetime(2018, 11, 15, 17, 0, 4, tzinfo=UTC),
                               upload_date=date(2018, 11, 15))
    assert vd.tiene_hora_y_zona(fecha_de_subida(con_hora))
    solo_dia = SimpleNamespace(published_at=None, upload_date=date(2018, 11, 15))
    assert fecha_de_subida(solo_dia) == "2018-11-15"
    assert fecha_de_subida(SimpleNamespace(published_at=None, upload_date=None)) is None


def test_youtube_en_tandas_y_sin_inventar_los_que_no_vuelven():
    pedidos = []

    def responder(request: httpx.Request) -> httpx.Response:
        ids = request.url.params["id"].split(",")
        pedidos.append(len(ids))
        # «borrado» no vuelve: así responde la API con un vídeo privado o eliminado.
        return httpx.Response(200, json={"items": [
            {"id": i, "snippet": {"publishedAt": "2020-01-02T03:04:05Z"}}
            for i in ids if i != "borrado"]})

    ids = [f"v{n}" for n in range(60)] + ["borrado", "v0"]
    with httpx.Client(transport=httpx.MockTransport(responder)) as c:
        out = vd.published_at_de_youtube(ids, key="k", client=c)
    assert pedidos == [50, 11]                 # 61 únicos, de 50 en 50
    assert "borrado" not in out and len(out) == 60
    assert out["v0"] == "2020-01-02T03:04:05Z"


def test_backfill_completa_los_dicts_sin_pisar_los_buenos():
    from scripts.seo.backfill_video_dates import aplicar, con_fecha

    fechas = {"a": "2020-01-02T03:04:05Z"}
    assert con_fecha({"youtube_id": "a", "upload_date": "2020-01-02"}, fechas)[
        "upload_date"] == "2020-01-02T03:04:05Z"
    ya = {"youtube_id": "a", "upload_date": "2019-05-05T10:00:00Z"}
    assert con_fecha(ya, fechas) is ya
    sin = {"youtube_id": "z", "upload_date": None}
    assert con_fecha(sin, fechas) is sin       # YouTube no lo devolvió: se queda igual

    rel = SimpleNamespace(youtube_id="a", published_at=None)
    huerfano = SimpleNamespace(youtube_id="z", published_at=None)
    post = SimpleNamespace(video={"youtube_id": "a", "upload_date": "2020-01-02"},
                           videos=[{"youtube_id": "a", "upload_date": None}, sin])
    intacto = SimpleNamespace(video=sin, videos=None)
    cuenta = aplicar([rel, huerfano], [post, intacto], fechas)
    assert cuenta == {"related_videos": 1, "posts_y_propuestas": 1}
    assert rel.published_at == datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert huerfano.published_at is None
    assert post.video["upload_date"] == post.videos[0]["upload_date"] == "2020-01-02T03:04:05Z"
    assert post.videos[1] is sin
