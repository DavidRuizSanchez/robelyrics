"""Tests de los clips de vídeo de terceros.

Lo que se blinda aquí es lo que hace asumible la decisión editorial de publicar
sin pedir permiso previo: que quede registrada la procedencia, que el tramo sea
corto, que la atribución viaje con la pieza y que la retirada funcione.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem, InstagramQueueMedia, VideoClip
from app.services.instagram import video_clips as vc


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    # Pedir un clip crea también su publicación, así que hacen falta sus tablas
    # (`media` es una relación selectin y se carga al refrescar el item).
    VideoClip.__table__.create(engine)
    InstagramQueueItem.__table__.create(engine)
    InstagramQueueMedia.__table__.create(engine)
    with Session(engine) as s:
        yield s


URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
TEMA = "Concierto de Extremoduro en la sala Vértigo, 1993"


# --------------------------------------------------------------------------- #
# Identificación de la fuente
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "url,esperado",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://vimeo.com/12345", None),
        ("cualquier cosa", None),
    ],
)
def test_extrae_el_id_del_video(url, esperado):
    assert vc.extraer_video_id(url) == esperado


# --------------------------------------------------------------------------- #
# Alta: tramos y procedencia
# --------------------------------------------------------------------------- #
def test_registra_la_procedencia(db):
    clip = vc.solicitar(db, URL, 10, 40, subtitle=TEMA, requested_by="admin@x.com")
    assert clip.video_id == "dQw4w9WgXcQ"
    assert clip.url == URL
    assert clip.requested_by == "admin@x.com"
    assert clip.status == "requested"


def test_el_clip_crea_su_propia_publicacion(db):
    """El clip ES el tema, no un formato colgado sobre un post que iba de otra
    cosa: pedirlo deja ya su publicación en la cola, con su título."""
    clip = vc.solicitar(db, URL, 10, 40, subtitle=TEMA)
    item = db.get(InstagramQueueItem, clip.queue_item_id)
    assert item is not None
    assert item.title == TEMA
    assert item.content_type == "clip"
    assert item.media_type == "CLIP"
    assert item.media_locked is True          # no lo toca el repartidor
    assert item.content_key == "clip:dQw4w9WgXcQ:10-40"


def test_sin_tema_no_hay_clip(db):
    """El tema es el título del post: sin él saldría una publicación muda."""
    with pytest.raises(ValueError, match="de qué va"):
        vc.solicitar(db, URL, 0, 20)


def test_un_clip_se_publica_como_VIDEO_no_como_foto(db, monkeypatch):
    """Regresión: `publish` solo mandaba a `post_reel` si el formato era REELS.

    CLIP caía al `else` y acababa en `post_photo` con una URL de .mp4, así que
    NINGÚN clip podía publicarse. Un clip es vídeo, igual que un reel.
    """
    from app.db.models import InstagramQueueMedia
    from app.services.instagram import publisher

    clip = vc.solicitar(db, URL, 0, 20, subtitle=TEMA)
    item = db.get(InstagramQueueItem, clip.queue_item_id)
    item.media_type = "CLIP"
    item.caption = "un pie de foto"
    item.media.append(InstagramQueueMedia(
        position=0, kind="video", role="clip",
        url="https://res.cloudinary.com/x/video/upload/clip.mp4",
        cloudinary_public_id="x/clip",
    ))
    db.commit()

    usados: list[str] = []
    monkeypatch.setattr(publisher.graph_api, "connection_is_healthy",
                        lambda: (True, "ok", None))
    monkeypatch.setattr(publisher.cloudinary_upload, "upload_video",
                        lambda p: {"url": "https://cdn/x.mp4", "public_id": "x"})
    monkeypatch.setattr(publisher.graph_api, "post_reel",
                        lambda url, cap: (usados.append("reel"), ("17", "ok"))[1])
    monkeypatch.setattr(publisher.graph_api, "post_photo",
                        lambda url, cap: (usados.append("photo"), ("17", "ok"))[1])
    monkeypatch.setattr(publisher.community, "comentar_post",
                        lambda mid, cap: (True, ""))

    publisher.publish(db, item)
    assert usados == ["reel"]          # jamás "photo": es un .mp4
    assert item.status == "published"
    db.refresh(clip)
    assert clip.status == "published"  # la ficha de procedencia se cierra


def test_rechaza_una_url_que_no_es_youtube(db):
    with pytest.raises(ValueError, match="YouTube"):
        vc.solicitar(db, "https://example.com/v", 0, 30)


def test_rechaza_un_tramo_demasiado_largo(db):
    """Un clip corto es más defendible y funciona mejor."""
    with pytest.raises(ValueError, match="pasa de"):
        vc.solicitar(db, URL, 0, vc.MAX_CLIP_S + 1)


def test_rechaza_un_tramo_ridiculo(db):
    with pytest.raises(ValueError, match="menos de"):
        vc.solicitar(db, URL, 0, 1, subtitle=TEMA)


def test_el_tope_es_de_un_minuto():
    assert vc.MAX_CLIP_S <= 60


# --------------------------------------------------------------------------- #
# Atribución: viaja con la pieza, no solo en el caption
# --------------------------------------------------------------------------- #
def test_la_atribucion_nombra_al_canal(db):
    clip = vc.solicitar(db, URL, 0, 20, subtitle=TEMA)
    clip.channel_title = "Juancares"
    assert "Juancares" in clip.atribucion


def test_hay_atribucion_aunque_falte_el_canal(db):
    clip = vc.solicitar(db, URL, 0, 20, subtitle=TEMA)
    assert clip.atribucion.strip()


def test_el_credito_se_quema_en_el_video():
    """Debe ir sobreimpreso: así viaja con la pieza aunque la reenvíen."""
    import inspect
    fuente = inspect.getsource(vc.descargar_y_recortar)
    assert "drawtext" in fuente
    assert "credito" in fuente


def test_solo_se_descarga_el_tramo_pedido():
    """No se baja el vídeo entero: menos huella y menos exposición."""
    import inspect
    fuente = inspect.getsource(vc.descargar_y_recortar)
    assert "download_ranges" in fuente


def test_escapa_el_texto_para_ffmpeg():
    """Un título con comillas o dos puntos rompería el filtro drawtext."""
    salida = vc._escapar_drawtext("Robe: 'el directo' 100%")
    assert "\\:" in salida
    assert "'" not in salida
    assert "\\%" in salida


# --------------------------------------------------------------------------- #
# Cola
# --------------------------------------------------------------------------- #
def test_los_pendientes_incluyen_los_fallidos(db):
    a = vc.solicitar(db, URL, 0, 20, subtitle=TEMA)
    b = vc.solicitar(db, "https://youtu.be/abcdefghijk", 0, 20, subtitle="Otro tema")
    b.status, b.attempts = "failed", 1
    db.commit()
    ids = {c.id for c in vc.pendientes(db)}
    assert ids == {a.id, b.id}


def test_deja_de_reintentar_tras_varios_fallos(db):
    c = vc.solicitar(db, URL, 0, 20, subtitle=TEMA)
    c.status, c.attempts = "failed", 3
    db.commit()
    assert vc.pendientes(db, max_intentos=3) == []


def test_lo_ya_publicado_no_se_vuelve_a_bajar(db):
    c = vc.solicitar(db, URL, 0, 20, subtitle=TEMA)
    c.status = "published"
    db.commit()
    assert vc.pendientes(db) == []


# --------------------------------------------------------------------------- #
# Retirada: la válvula ante una reclamación
# --------------------------------------------------------------------------- #
def test_retirar_deja_constancia(db, monkeypatch):
    from app.services.instagram import cloudinary_upload
    monkeypatch.setattr(cloudinary_upload, "destroy", lambda *a, **k: True)

    clip = vc.solicitar(db, URL, 0, 20, subtitle=TEMA)
    clip.status = "published"
    clip.cloudinary_public_id = "abc/def"
    db.commit()

    ok, _ = vc.retire(db, clip, motivo="reclamación del canal")
    assert ok
    assert clip.status == "retired"
    assert clip.retired_at is not None
    assert clip.retired_reason == "reclamación del canal"


def test_si_falla_el_borrado_externo_se_marca_igual(db, monkeypatch):
    """Ante una reclamación, lo peor sería no dejar rastro de la retirada."""
    from app.services.instagram import cloudinary_upload

    def peta(*a, **k):
        raise RuntimeError("Cloudinary caído")

    monkeypatch.setattr(cloudinary_upload, "destroy", peta)

    clip = vc.solicitar(db, URL, 0, 20, subtitle=TEMA)
    clip.status = "published"
    clip.cloudinary_public_id = "abc/def"
    db.commit()

    ok, msg = vc.retire(db, clip, motivo="aviso")
    assert not ok
    assert "Cloudinary" in msg
    assert clip.status == "retired"       # se marca igualmente
    assert clip.retired_reason == "aviso"


# --------------------------------------------------------------------------- #
# Montaje: el escalado tiene que valer para CUALQUIER proporción de origen
# --------------------------------------------------------------------------- #
# Falló en la primera prueba real con un vídeo de YouTube: un 16:9 escalado a
# ancho 1080 queda en 1080x608, y recortar 1920 de alto de eso revienta con
# "Invalid too big or non positive size for width '1080' or height '1920'".

def test_el_fondo_escala_para_cubrir_y_el_primer_plano_para_caber():
    import inspect
    fuente = inspect.getsource(vc.descargar_y_recortar)
    assert "force_original_aspect_ratio=increase" in fuente, (
        "el fondo debe CUBRIR el lienzo antes de recortar"
    )
    assert "force_original_aspect_ratio=decrease" in fuente, (
        "el primer plano debe CABER entero"
    )


@pytest.mark.parametrize(
    "ancho,alto", [(1920, 1080), (1080, 1080), (720, 1280), (640, 480)]
)
def test_el_montaje_da_9_16_venga_como_venga(ancho, alto, tmp_path):
    """Se monta un vídeo sintético de cada proporción y se comprueba la salida."""
    import shutil
    import subprocess

    if not shutil.which("ffmpeg"):
        pytest.skip("sin ffmpeg")

    origen = str(tmp_path / "in.mp4")
    salida = str(tmp_path / "out.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", f"testsrc=size={ancho}x{alto}:rate=25:duration=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", origen],
        check=True,
    )
    filtros = [
        f"[0:v]scale={vc.ANCHO}:{vc.ALTO}:force_original_aspect_ratio=increase,"
        f"crop={vc.ANCHO}:{vc.ALTO},boxblur=28:2[bg]",
        f"[0:v]scale={vc.ANCHO}:{vc.ALTO}:force_original_aspect_ratio=decrease[fg]",
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[v]",
    ]
    vc._ffmpeg([
        "-i", origen, "-filter_complex", ";".join(filtros), "-map", "[v]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", "1", salida,
    ])
    medida = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", salida],
        capture_output=True, text=True,
    )
    assert medida.stdout.strip() == f"{vc.ANCHO},{vc.ALTO}"


def test_el_borrado_invalida_la_cache_del_cdn():
    """Sin `invalidate`, Cloudinary borra el asset pero el CDN lo sigue sirviendo.

    Comprobado en la primera prueba de retirada: el fichero ya no existía en la
    cuenta y su URL seguía devolviendo HTTP 200.
    """
    import inspect
    from app.services.instagram import cloudinary_upload
    assert "invalidate=True" in inspect.getsource(cloudinary_upload.destroy)


def test_la_retirada_no_promete_lo_que_no_puede(db, monkeypatch):
    """La invalidación del CDN tarda: el mensaje no debe decir que ya no existe."""
    from app.services.instagram import cloudinary_upload
    monkeypatch.setattr(cloudinary_upload, "destroy", lambda *a, **k: True)

    clip = vc.solicitar(db, URL, 0, 20, subtitle=TEMA)
    clip.cloudinary_public_id = "x/y"
    db.commit()
    _, msg = vc.retire(db, clip, motivo="aviso")
    assert "CDN" in msg or "caché" in msg


# --------------------------------------------------------------------------- #
# Canales vetados: los oficiales no
# --------------------------------------------------------------------------- #
# Decisión del usuario tras ver que el primer clip de prueba salió del canal
# «Extremoduro (Oficial)». Publicar de un canal de fan y del canal oficial de la
# banda o su discográfica no tienen el mismo riesgo: el titular de derechos es
# quien reclamaría y Meta puede tumbar el post automáticamente.

@pytest.mark.parametrize(
    "canal",
    [
        "Extremoduro (Oficial)",
        "Robe Iniesta Official",
        "ExtremoduroVEVO",
        "Extremoduro - Topic",
        "Warner Music Spain",
        "Sony Music España",
        "DRO East West",
    ],
)
def test_los_canales_oficiales_estan_vetados(canal):
    assert vc.canal_vetado(canal) is not None


@pytest.mark.parametrize(
    "canal",
    ["Juancares", "Rock del Bueno", "Archivo Extremoduro Fans", "El Faro (SER)"],
)
def test_los_canales_de_fan_y_archivo_valen(canal):
    assert vc.canal_vetado(canal) is None


def test_sin_canal_no_se_veta_a_ciegas():
    assert vc.canal_vetado("") is None
    assert vc.canal_vetado(None) is None


def test_el_veto_se_comprueba_con_el_canal_REAL():
    """No con lo que uno crea al pegar la URL: el nombre lo da yt-dlp."""
    import inspect
    fuente = inspect.getsource(vc.descargar_y_recortar)
    assert "canal_vetado(canal_real)" in fuente
    assert 'info or {}).get("uploader")' in fuente


# --------------------------------------------------------------------------- #
# Un fallo al preparar no puede tumbar el cron ni atascar la cola
# --------------------------------------------------------------------------- #
def test_si_preparar_falla_el_item_queda_failed_y_no_atasca(db, monkeypatch):
    """`publish_next` llama a `publish()` sin try/except y `next_pending` solo
    mira (pending, prepared): si el item se quedara `pending`, el cron lo
    reelegiría cada 15 min y la cola entera se pararía detrás de él."""
    from app.services.instagram import publisher

    clip = vc.solicitar(db, URL, 0, 20, subtitle=TEMA)
    item = db.get(InstagramQueueItem, clip.queue_item_id)

    def _revienta(_db, _item):
        raise RuntimeError("este post es de formato «clip externo» y no tiene ninguno")

    monkeypatch.setattr(publisher, "prepare", _revienta)
    res = publisher.publish(db, item)

    assert res.status == "failed"
    assert "clip externo" in (res.error or "")
    # Y ya no lo devuelve el goteo: la cola sigue corriendo.
    assert publisher.next_pending(db) is None


def test_un_clip_bajandose_no_marca_el_post_como_fallido(db, monkeypatch):
    """Regresión del 29-jul: el goteo llegó al post NUEVE MINUTOS antes de que
    el daemon terminara de bajar el vídeo y lo dejó `failed` para siempre.

    «Aún no está listo» no es «está roto»."""
    from app.services.instagram import publisher

    clip = vc.solicitar(db, URL, 0, 20, subtitle=TEMA)   # nace en `requested`
    item = db.get(InstagramQueueItem, clip.queue_item_id)
    item.status = "pending"
    db.commit()

    def _aun_no(_db, _item):
        raise publisher.MaterialPendiente("el clip #1 aún se está bajando")

    monkeypatch.setattr(publisher, "prepare", _aun_no)
    res = publisher.publish(db, item)
    assert res.status == "pending", "no puede quedar fallido: el vídeo viene en camino"
    assert not res.error


def test_un_clip_bajandose_no_atasca_la_cola(db):
    """Y mientras tanto no puede ser el elegido del goteo: iría por `position`
    y siempre saldría el mismo, con toda la cola parada detrás."""
    from app.services.instagram import publisher

    clip = vc.solicitar(db, URL, 0, 20, subtitle=TEMA)
    pendiente = db.get(InstagramQueueItem, clip.queue_item_id)
    pendiente.status = "pending"
    db.commit()
    assert publisher.next_pending(db) is None

    # En cuanto el daemon lo deja listo, ya sí entra en el goteo.
    clip.status = "ready"
    clip.url_cdn = "https://res.cloudinary.com/x/video/upload/clip.mp4"
    db.commit()
    assert publisher.next_pending(db) is not None


def test_un_clip_ya_en_el_cdn_no_se_vuelve_a_subir(db, monkeypatch):
    """Regresión (29-jul-2026): el clip de la sala Vértigo no se publicó.

    El daemon de la Mac baja el vídeo y lo sube DIRECTO a Cloudinary, así que la
    pieza llega con `url` puesta y sin `local_path` — nunca pasa por el /tmp del
    servidor. `_media_lista` lo daba por bueno justamente por eso, pero el bucle
    de subida no hacía la misma comprobación y llamaba a `upload_video(None)`:
    «expected str, bytes or os.PathLike object, not NoneType». El post quedaba
    `failed` sin haber llegado a Meta.

    El test anterior no lo cazó porque su mock de `upload_video` aceptaba `None`
    tan campante. Aquí se comprueba el invariante de verdad: si ya está en el
    CDN, no se sube nada.
    """
    from app.db.models import InstagramQueueMedia
    from app.services.instagram import publisher

    CDN = "https://res.cloudinary.com/x/video/upload/clip.mp4"
    clip = vc.solicitar(db, URL, 0, 20, subtitle=TEMA)
    item = db.get(InstagramQueueItem, clip.queue_item_id)
    item.media_type = "CLIP"
    item.caption = "un pie de foto"
    item.media.append(InstagramQueueMedia(
        position=0, kind="video", role="clip",
        url=CDN, cloudinary_public_id="x/clip", local_path=None,
    ))
    db.commit()

    subidas: list = []

    def _no_deberia(path):
        subidas.append(path)
        raise TypeError(
            "expected str, bytes or os.PathLike object, not NoneType"
        )

    monkeypatch.setattr(publisher.graph_api, "connection_is_healthy",
                        lambda: (True, "ok", None))
    monkeypatch.setattr(publisher.cloudinary_upload, "upload_video", _no_deberia)
    monkeypatch.setattr(publisher.cloudinary_upload, "upload", _no_deberia)
    monkeypatch.setattr(publisher.graph_api, "post_reel",
                        lambda url, cap: ("17", "ok"))
    monkeypatch.setattr(publisher.community, "comentar_post",
                        lambda mid, cap: (True, ""))

    publisher.publish(db, item)

    assert subidas == [], f"no había nada que subir y se intentó: {subidas}"
    assert item.status == "published"
    assert item.error is None
    assert item.media[0].url == CDN     # se conserva la del daemon


def test_el_clip_se_publica_con_la_url_que_ya_tenia(db, monkeypatch):
    """Y lo que se le manda a Meta es esa misma URL, no otra."""
    from app.db.models import InstagramQueueMedia
    from app.services.instagram import publisher

    CDN = "https://res.cloudinary.com/x/video/upload/vertigo.mp4"
    clip = vc.solicitar(db, URL, 0, 20, subtitle=TEMA)
    item = db.get(InstagramQueueItem, clip.queue_item_id)
    item.media_type = "CLIP"
    item.caption = "un pie de foto"
    item.media.append(InstagramQueueMedia(
        position=0, kind="video", role="clip", url=CDN, local_path=None,
    ))
    db.commit()

    enviadas: list[str] = []
    monkeypatch.setattr(publisher.graph_api, "connection_is_healthy",
                        lambda: (True, "ok", None))
    monkeypatch.setattr(publisher.graph_api, "post_reel",
                        lambda url, cap: (enviadas.append(url), ("17", "ok"))[1])
    monkeypatch.setattr(publisher.community, "comentar_post",
                        lambda mid, cap: (True, ""))

    publisher.publish(db, item)
    assert enviadas == [CDN]
