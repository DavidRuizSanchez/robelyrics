"""Fotos reales antes que arte IA (09-11-2026).

Reconstruido el último mes: 12 de 51 posts salieron con IA, y la mitad eran
posts del blog sin hero cuyo TÍTULO nombraba un disco. Aquí: una canción ya
identificada lleva a la portada de su disco, y el texto libre no adivina
canciones (la colisión de «La Carrera»).
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.instagram import album_cover


class _DB:
    """Solo responde a la consulta de discos: (título, slug, portada)."""

    def __init__(self, discos):
        self._discos = discos

    def execute(self, _stmt):
        return SimpleNamespace(all=lambda: list(self._discos))


DISCOS = [("Destrozares, canciones para el final de los tiempos", "destrozares",
           "/album-covers/destrozares.jpg"),
          ("Agila", "agila", "/album-covers/agila.jpg")]


def test_el_disco_nombrado_en_el_texto_da_su_portada(monkeypatch):
    monkeypatch.setattr(album_cover, "_load_media", lambda: {})
    r = album_cover.find(_DB(DISCOS), {"title": "La Gira de Agila, 1996"})
    assert r and r["url"].endswith("/album-covers/agila.jpg")


def test_una_cancion_identificada_da_la_portada_de_su_disco(monkeypatch):
    monkeypatch.setattr(album_cover, "_load_media", lambda: {})
    monkeypatch.setattr(album_cover, "_disco_de_cancion", lambda db, sid: (
        "destrozares", "destrozares", "/album-covers/destrozares.jpg") if sid == 135 else None)
    r = album_cover.find(_DB(DISCOS), {"title": "Harto de esperar a que viniera a verme"},
                         song_id=135)
    assert r and r["url"].endswith("/album-covers/destrozares.jpg")


def test_sin_disco_ni_cancion_identificada_no_se_adivina(monkeypatch):
    """«en la carrera» en un texto no es «La Carrera»: sin `song_id`, nada."""
    monkeypatch.setattr(album_cover, "_load_media", lambda: {})
    assert album_cover.find(_DB(DISCOS), {"title": "Una vida en la carrera del rock"}) is None
