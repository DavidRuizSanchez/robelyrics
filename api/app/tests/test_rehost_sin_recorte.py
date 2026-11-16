"""Una cabecera del blog se re-aloja entera, sin recortar (16-11-2026).

`_rehost_to_cloudinary` pasaba por `imaging._fetch_image`, que recorta a cuadrado
para Instagram: el cartel de Flores Amarillas 2027 (1200×1600) quedó en 1080×1080
sin la fecha ni los logos.
"""
from __future__ import annotations

from PIL import Image

from app.services import blog_hero
from app.services.instagram import cloudinary_upload, imaging


def _subida(monkeypatch, original: Image.Image) -> tuple[int, int]:
    medidas = {}

    def subir(path, folder="x"):
        with Image.open(path) as img:
            medidas["size"] = img.size
        return "https://res.cloudinary.com/demo/image/upload/v1/entreinteriores-blog/x.jpg"

    monkeypatch.setattr(imaging, "descargar_imagen", lambda url, timeout=60.0: original)
    monkeypatch.setattr(cloudinary_upload, "upload", subir)
    assert blog_hero._rehost_to_cloudinary("https://img.europapress.es/cartel.jpg")
    return medidas["size"]


def test_un_cartel_vertical_se_sube_entero(monkeypatch):
    assert _subida(monkeypatch, Image.new("RGB", (1200, 1600), "yellow")) == (1200, 1600)


def test_un_original_enorme_se_reduce_sin_cambiar_la_proporcion(monkeypatch):
    assert _subida(monkeypatch, Image.new("RGB", (6000, 4000), "white")) == (2400, 1600)


def test_instagram_sigue_recortando_a_cuadrado(monkeypatch):
    monkeypatch.setattr(imaging, "descargar_imagen",
                        lambda url, timeout=60.0: Image.new("RGB", (1200, 1600)))
    assert imaging._fetch_image("https://x/y.jpg").size == imaging.SIZE
