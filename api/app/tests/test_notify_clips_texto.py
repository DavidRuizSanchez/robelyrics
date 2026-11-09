"""El correo de un clip enseña el texto que se publicará, y sin texto no hay botón."""
from __future__ import annotations

from types import SimpleNamespace

from scripts.instagram import notify_clips as nc


def _clip():
    return SimpleNamespace(id=1, start_s=10.0, end_s=40.0, url_cdn="https://x/v.mp4",
                           overlay="¡Qué cierre!\n«Destrozares» · Vigo · 2024")


def _item(caption):
    return SimpleNamespace(id=7, title="El final de «Destrozares»", caption=caption,
                           notas_internas="Momento: final", summary=None)


def test_el_correo_lleva_el_texto_exacto_y_el_boton(monkeypatch):
    monkeypatch.setattr(nc, "create_clip_action_token", lambda cid, a: f"tok-{a}")
    html = nc._ficha_html(_clip(), _item("El final de «Destrozares» <en Vigo>"), "https://s")
    assert "Texto que se publicará" in html
    assert "&lt;en Vigo&gt;" in html          # escapado
    assert "Publicar este" in html


def test_sin_texto_publicable_no_hay_boton_de_publicar(monkeypatch):
    monkeypatch.setattr(nc, "create_clip_action_token", lambda cid, a: f"tok-{a}")
    html = nc._ficha_html(_clip(), _item(None), "https://s",
                          problema="el texto del clip no pasa las guardas")
    assert "Publicar este" not in html
    assert "no pasa las guardas" in html
    assert "Descartar" in html
