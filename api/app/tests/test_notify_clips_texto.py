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


# --------------------------------------------------------------------------- #
# Al correo solo va lo que se puede aprobar (David, 20-11-2026)
# --------------------------------------------------------------------------- #
class _Db:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


def _repartir(monkeypatch, estados, *, dry_run=False):
    descartes = []
    monkeypatch.setattr(nc, "estado_del_texto", lambda db, item: estados[item.id])
    monkeypatch.setattr("app.services.instagram.video_clips.descartar",
                        lambda db, item, motivo: descartes.append((item.id, motivo)))
    pares = [(SimpleNamespace(id=100 + i), SimpleNamespace(id=i, title=f"clip {i}"))
             for i in estados]
    aprobables, descartados, en_espera = nc.repartir(_Db(), pares, dry_run=dry_run)
    return ([i.id for _c, i in aprobables], [i.id for _c, i, _m in descartados],
            [i.id for _c, i, _m in en_espera], descartes)


def test_un_clip_sin_texto_publicable_se_descarta_y_no_va_al_correo(monkeypatch):
    """Llegaban cuatro clips sin botón de publicar, y al día siguiente otra vez."""
    aprobables, descartados, en_espera, descartes = _repartir(monkeypatch, {
        1: ("ok", None),
        2: ("sin_texto", "clip: cita «Mayéutica», que no es la canción del clip ni su disco"),
        3: ("fallo", "el modelo no responde")})
    assert aprobables == [1] and descartados == [2] and en_espera == [3]
    assert descartes == [(2, "sin texto publicable: clip: cita «Mayéutica», que no es la "
                             "canción del clip ni su disco")]


def test_un_fallo_tecnico_no_descarta_el_clip(monkeypatch):
    aprobables, descartados, en_espera, descartes = _repartir(
        monkeypatch, {3: ("fallo", "el modelo no responde")})
    assert (aprobables, descartados, en_espera, descartes) == ([], [], [3], [])


def test_el_ensayo_no_descarta_nada(monkeypatch):
    _a, descartados, _e, descartes = _repartir(
        monkeypatch, {2: ("sin_texto", "no pasa las guardas")}, dry_run=True)
    assert descartados == [2] and descartes == []
