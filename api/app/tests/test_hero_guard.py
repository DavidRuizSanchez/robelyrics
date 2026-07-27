"""Gate de relevancia del hero: confía en el arte propio, verifica lo web y
degrada con seguridad.
"""
from __future__ import annotations

import app.services.hero_guard as hg


def test_sin_imagen_pasa():
    assert hg.verify_hero(None, subject="Robe").ok
    assert hg.verify_hero({"url": ""}, subject="Robe").ok


def test_fuente_de_confianza_no_usa_vision(monkeypatch):
    # Si tocara visión, fallaría (no hay red); debe pasar por confianza.
    monkeypatch.setattr(hg, "_vision_relevance",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía ver")))
    arte = {"url": "u", "attribution": "Ilustración editorial de Entre Interiores para «X»"}
    assert hg.verify_hero(arte, subject="X").ok
    portada = {"url": "u", "attribution": "Portada de «El Vuelo del Fénix»"}
    assert hg.verify_hero(portada, subject="X").ok


def test_web_irrelevante_se_rechaza(monkeypatch):
    monkeypatch.setattr(hg, "_vision_relevance",
                        lambda url, subj, ents: hg.HeroVerdict(False, "muestra a otra persona", "mujer"))
    v = hg.verify_hero({"url": "u", "attribution": "Foto web"}, subject="Rosendo")
    assert not v.ok
    assert "otra persona" in v.reason


def test_web_relevante_pasa(monkeypatch):
    monkeypatch.setattr(hg, "_vision_relevance",
                        lambda url, subj, ents: hg.HeroVerdict(True, "es el sujeto", "cantante"))
    assert hg.verify_hero({"url": "u", "attribution": "Foto web"}, subject="Robe").ok


def test_gate_desactivado_no_bloquea(monkeypatch):
    monkeypatch.setenv("HERO_VISION_GATE", "0")
    monkeypatch.setattr(hg, "_vision_relevance",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía ver")))
    assert hg.verify_hero({"url": "u", "attribution": "Foto web"}, subject="X").ok
