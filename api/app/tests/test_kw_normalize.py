"""Búsquedas de descarga de música: prohibidas (criterio de David, 26-10-2026)."""
from __future__ import annotations

import pytest

from app.services.kw_normalize import es_descarga


@pytest.mark.parametrize("kw", [
    "descargar discografía extremoduro",
    "extremoduro descarga gratis",
    "robe mayéutica mp3",
    "extremoduro discografia torrent",
    "agila flac",
    "extremoduro discografia mega",
    "la ley innata zip",
    "extremoduro rar",
    "Download Extremoduro",
])
def test_descargas_se_reconocen(kw):
    assert es_descarga(kw)


@pytest.mark.parametrize("kw", [
    "cuantas canciones tiene extremoduro",
    "ariel rot conciertos",
    "megafono extremoduro",        # «mega» solo como palabra entera
    "zipi y zape",
    "extremoduro rarezas",
])
def test_lo_demas_no(kw):
    assert not es_descarga(kw)
