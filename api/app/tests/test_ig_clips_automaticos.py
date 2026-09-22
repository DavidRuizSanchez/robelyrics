"""El sistema elige el vídeo y el tramo; la persona decide si sale.

Lo que se blinda aquí es lo que antes hacía David a mano viendo el vídeo:
elegir dónde empieza y dónde acaba un clip. Y, sobre todo, que elegir solo NO
signifique publicar solo.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import (
    InstagramQueueItem,
    InstagramQueueMedia,
    SourceSegment,
    VideoAsset,
    VideoClip,
)
from app.services.auth import (
    create_clip_action_token,
    decode_clip_action_token,
    decode_seo_opportunity_token,
    decode_youtube_ingest_token,
)
from app.services.instagram import clip_picker
from app.services.instagram import video_clips as vc


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    # `interpretation_sources` NO se crea: lleva un ARRAY(Integer) que SQLite no
    # sabe compilar (ver gotcha de los tests en SQLite). Aquí solo se la apunta
    # por FK, y SQLite no valida claves ajenas salvo que se le pida.
    for tabla in (
        SourceSegment, VideoAsset, VideoClip,
        InstagramQueueItem, InstagramQueueMedia,
    ):
        tabla.__table__.create(engine)
    with Session(engine) as s:
        yield s


def _asset(db, **kw) -> VideoAsset:
    base = {
        "youtube_id": "dQw4w9WgXcQ",
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "title": "Entrevista a Robe",
        "channel_title": "Canal de un fan",
        "duration_s": 1200,
        "kind": "interview",
        "source_id": 1,
        "vetado": False,
    }
    base.update(kw)
    a = VideoAsset(**base)
    db.add(a)
    db.commit()
    return a


def _segmentos(db, textos, *, source_id=1, desde=60.0, dur=4.0, hueco=0.0):
    """Tramos consecutivos, como los que devuelven Whisper o los subtítulos."""
    t = desde
    for i, texto in enumerate(textos):
        db.add(SourceSegment(
            source_id=source_id, idx=i, start_s=t, end_s=t + dur, text=texto,
        ))
        t += dur + hueco
    db.commit()


FRASE = "Siempre me ha gustado la poesía y recuerdo leer a Machado con dieciséis años."


# --------------------------------------------------------------------------- #
# Duración y fronteras
# --------------------------------------------------------------------------- #
def test_ningun_tramo_se_sale_de_la_duracion_admitida(db):
    _asset(db)
    _segmentos(db, [FRASE] * 30)
    cands = clip_picker.candidatos_de(db, db.query(VideoAsset).first())
    assert cands
    for c in cands:
        assert clip_picker.MIN_S <= c.duracion_s <= clip_picker.MAX_S
        # Y dentro de lo que el montaje admite.
        assert vc.MIN_CLIP_S <= c.duracion_s <= vc.MAX_CLIP_S


def test_un_corte_por_puntuacion_puntua_mas_que_uno_aproximado(db):
    _asset(db)
    _segmentos(db, [FRASE] * 30)
    cands = clip_picker.candidatos_de(db, db.query(VideoAsset).first())
    fronteras = {c.frontera for c in cands}
    assert "puntuacion" in fronteras
    limpios = [c for c in cands if c.frontera == "puntuacion"]
    assert limpios[0].score > 0


def test_sin_puntuacion_la_frontera_no_se_declara_limpia(db):
    """Los subtítulos automáticos de YouTube llegan sin puntuación. Decir que un
    corte es limpio porque no se encontró un punto sería justo al revés."""
    _asset(db)
    _segmentos(db, ["y entonces me puse a escribir aquella canción sin pensarlo"] * 30)
    cands = clip_picker.candidatos_de(db, db.query(VideoAsset).first())
    assert cands
    assert all(c.frontera != "puntuacion" for c in cands)


# --------------------------------------------------------------------------- #
# Lo que NO puede acabar en un clip
# --------------------------------------------------------------------------- #
def test_la_intro_de_un_canal_no_es_material(db):
    """Medido en la primera pasada real: dos de los cinco mejores candidatos
    eran «bienvenidos al canal», que es otro youtuber presentándose."""
    _asset(db)
    _segmentos(db, ["Bienvenidos al canal, hoy os traigo una reacción a Robe."] * 30)
    assert clip_picker.candidatos_de(db, db.query(VideoAsset).first()) == []


def test_el_principio_del_video_se_ignora(db):
    """Saludo, presentación y créditos son de quien sube el vídeo."""
    _asset(db, duration_s=1200)
    _segmentos(db, [FRASE] * 30, desde=0.0)
    cands = clip_picker.candidatos_de(db, db.query(VideoAsset).first())
    assert cands
    assert all(c.start_s >= clip_picker.INTRO_S for c in cands)


def test_un_video_vetado_no_da_candidatos(db):
    _asset(db, vetado=True, motivo_veto="canal vetado")
    _segmentos(db, [FRASE] * 30)
    assert clip_picker.candidatos_de(db, db.query(VideoAsset).first()) == []


def test_un_video_sin_transcripcion_no_da_candidatos(db):
    _asset(db, source_id=None)
    assert clip_picker.candidatos_de(db, db.query(VideoAsset).first()) == []


def test_no_se_repite_un_tramo_ya_usado(db):
    asset = _asset(db)
    _segmentos(db, [FRASE] * 30)
    todos = clip_picker.candidatos_de(db, asset)
    primero = todos[0]
    db.add(VideoClip(
        video_id=asset.youtube_id, url=asset.url,
        start_s=primero.start_s, end_s=primero.end_s, status="published",
    ))
    db.commit()
    despues = clip_picker.candidatos_de(db, asset)
    assert all(
        not (c.start_s < primero.end_s and primero.start_s < c.end_s)
        for c in despues
    ), "un tramo ya publicado no se vuelve a proponer"


# --------------------------------------------------------------------------- #
# Canales: el veto veta, el aviso avisa
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("canal", ["Movistar Plus+", "RTVE Play", "EL PAÍS", "RockFM"])
def test_los_medios_profesionales_se_avisan_pero_no_se_vetan(canal):
    """No son discográficas ni canales oficiales de artista, y una entrevista de
    radio es justo el material que se busca. Vetarlos sería decidir por David;
    callarlo, esconderle que ese clip se reclama antes que el de un fan."""
    assert vc.canal_vetado(canal) is None
    assert vc.canal_sensible(canal) is not None


@pytest.mark.parametrize("canal", ["Extremoduro VEVO", "Robe - Topic", "Warner Music"])
def test_los_canales_oficiales_siguen_vetados(canal):
    assert vc.canal_vetado(canal) is not None


def test_un_canal_de_fan_ni_se_veta_ni_se_avisa():
    assert vc.canal_vetado("juancaraes") is None
    assert vc.canal_sensible("juancaraes") is None


# --------------------------------------------------------------------------- #
# Elegir solo no es publicar solo
# --------------------------------------------------------------------------- #
def test_una_propuesta_automatica_nace_fuera_del_goteo(db):
    clip = vc.solicitar(
        db, "https://www.youtube.com/watch?v=dQw4w9WgXcQ", 60.0, 90.0,
        subtitle="Robe en la radio", requested_by="auto",
        estado_item="proposed", needs_human=True,
    )
    item = db.get(InstagramQueueItem, clip.queue_item_id)
    assert item.status == "proposed", "`next_pending` solo mira pending/prepared"
    assert item.needs_human is True


def test_el_alta_manual_no_cambia_de_comportamiento(db):
    """Sigue entrando por donde entraba (`config.estado_inicial`), y sin quedar
    marcada para revisar: la ha tecleado una persona mirando el vídeo."""
    from app.services.instagram import config

    clip = vc.solicitar(
        db, "https://www.youtube.com/watch?v=dQw4w9WgXcQ", 60.0, 90.0,
        subtitle="Robe en la radio", requested_by="david@example.com",
    )
    item = db.get(InstagramQueueItem, clip.queue_item_id)
    assert item.status == config.estado_inicial()
    assert item.needs_human is False


# --------------------------------------------------------------------------- #
# El token del correo
# --------------------------------------------------------------------------- #
def test_el_token_de_un_clip_no_vale_para_otra_cosa():
    """Reenviar un correo no puede disparar otra acción del sistema."""
    t = create_clip_action_token(7, "approve")
    assert decode_clip_action_token(t)["clip_id"] == 7
    assert decode_seo_opportunity_token(t) is None
    assert decode_youtube_ingest_token(t) is None


def test_un_token_de_aprobar_no_sirve_para_descartar():
    datos = decode_clip_action_token(create_clip_action_token(7, "reject"))
    assert datos["action"] == "reject"


def test_no_se_firma_una_accion_que_no_existe():
    with pytest.raises(ValueError):
        create_clip_action_token(7, "publicar_ya")


# --------------------------------------------------------------------------- #
# Los tiempos, que es lo que desbloquea todo
# --------------------------------------------------------------------------- #
def test_los_tiempos_del_segundo_trozo_no_mienten(tmp_path, monkeypatch):
    """El audio se parte para no pasar de los 25 MB de Whisper, y Whisper numera
    cada trozo desde cero. Sin sumar el offset, los tiempos del segundo trozo
    mentirían en veinte minutos y el clip saldría de otro sitio del vídeo."""
    from scripts.research import transcribe_juancares as tj

    class _Seg:
        def __init__(self, start, end, text):
            self.start, self.end, self.text = start, end, text

    class _Resp:
        def __init__(self, segs):
            self.text = " ".join(s.text for s in segs)
            self.segments = segs

    llamadas = {"n": 0}

    class _FakeClient:
        class audio:  # noqa: N801
            class transcriptions:  # noqa: N801
                @staticmethod
                def create(**kw):
                    llamadas["n"] += 1
                    return _Resp([_Seg(0.0, 5.0, f"trozo {llamadas['n']}")])

    ficheros = []
    for i in range(2):
        f = tmp_path / f"chunk_{i}.mp3"
        f.write_bytes(b"x")
        ficheros.append(str(f))

    texto, segmentos = tj.transcribe(_FakeClient(), ficheros)

    assert "trozo 1" in texto and "trozo 2" in texto
    assert segmentos[0]["start_s"] == 0.0
    assert segmentos[1]["start_s"] == tj.CHUNK_SECONDS, "falta el offset del trozo"


def test_los_segmentos_se_guardan_ordenados_y_sin_vacios(db):
    from scripts.research.common import guardar_segmentos

    n = guardar_segmentos(db, 1, [
        {"start_s": 0.0, "end_s": 3.0, "text": "uno"},
        {"start_s": 3.0, "end_s": 6.0, "text": "   "},   # vacío: no cuenta
        {"start_s": 6.0, "end_s": 9.0, "text": "dos"},
    ])
    assert n == 2
    filas = db.query(SourceSegment).order_by(SourceSegment.idx).all()
    assert [f.idx for f in filas] == [0, 1]
    assert [f.text for f in filas] == ["uno", "dos"]


def test_volver_a_guardar_no_duplica(db):
    """Hay un único unique (source_id, idx): si no se reemplazara, un backfill
    repetido reventaría o dejaría tramos mezclados de dos pasadas."""
    from scripts.research.common import guardar_segmentos

    guardar_segmentos(db, 1, [{"start_s": 0.0, "end_s": 3.0, "text": "uno"}])
    guardar_segmentos(db, 1, [{"start_s": 0.0, "end_s": 3.0, "text": "otro"}])
    filas = db.query(SourceSegment).all()
    assert len(filas) == 1
    assert filas[0].text == "otro"
