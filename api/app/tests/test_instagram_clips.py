"""Tests de los clips de vídeo de terceros.

Lo que se blinda aquí es lo que hace asumible la decisión editorial de publicar
sin pedir permiso previo: que quede registrada la procedencia, que el tramo sea
corto, que la atribución viaje con la pieza y que la retirada funcione.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import VideoClip
from app.services.instagram import video_clips as vc


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    VideoClip.__table__.create(engine)
    with Session(engine) as s:
        yield s


URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


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
    clip = vc.solicitar(db, URL, 10, 40, requested_by="admin@x.com")
    assert clip.video_id == "dQw4w9WgXcQ"
    assert clip.url == URL
    assert clip.requested_by == "admin@x.com"
    assert clip.status == "requested"


def test_rechaza_una_url_que_no_es_youtube(db):
    with pytest.raises(ValueError, match="YouTube"):
        vc.solicitar(db, "https://example.com/v", 0, 30)


def test_rechaza_un_tramo_demasiado_largo(db):
    """Un clip corto es más defendible y funciona mejor."""
    with pytest.raises(ValueError, match="pasa de"):
        vc.solicitar(db, URL, 0, vc.MAX_CLIP_S + 1)


def test_rechaza_un_tramo_ridiculo(db):
    with pytest.raises(ValueError, match="menos de"):
        vc.solicitar(db, URL, 0, 1)


def test_el_tope_es_de_un_minuto():
    assert vc.MAX_CLIP_S <= 60


# --------------------------------------------------------------------------- #
# Atribución: viaja con la pieza, no solo en el caption
# --------------------------------------------------------------------------- #
def test_la_atribucion_nombra_al_canal(db):
    clip = vc.solicitar(db, URL, 0, 20)
    clip.channel_title = "Juancares"
    assert "Juancares" in clip.atribucion


def test_hay_atribucion_aunque_falte_el_canal(db):
    clip = vc.solicitar(db, URL, 0, 20)
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
    a = vc.solicitar(db, URL, 0, 20)
    b = vc.solicitar(db, "https://youtu.be/abcdefghijk", 0, 20)
    b.status, b.attempts = "failed", 1
    db.commit()
    ids = {c.id for c in vc.pendientes(db)}
    assert ids == {a.id, b.id}


def test_deja_de_reintentar_tras_varios_fallos(db):
    c = vc.solicitar(db, URL, 0, 20)
    c.status, c.attempts = "failed", 3
    db.commit()
    assert vc.pendientes(db, max_intentos=3) == []


def test_lo_ya_publicado_no_se_vuelve_a_bajar(db):
    c = vc.solicitar(db, URL, 0, 20)
    c.status = "published"
    db.commit()
    assert vc.pendientes(db) == []


# --------------------------------------------------------------------------- #
# Retirada: la válvula ante una reclamación
# --------------------------------------------------------------------------- #
def test_retirar_deja_constancia(db, monkeypatch):
    from app.services.instagram import cloudinary_upload
    monkeypatch.setattr(cloudinary_upload, "destroy", lambda *a, **k: True)

    clip = vc.solicitar(db, URL, 0, 20)
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

    clip = vc.solicitar(db, URL, 0, 20)
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
