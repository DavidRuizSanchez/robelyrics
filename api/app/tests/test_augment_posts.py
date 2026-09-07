"""Tests del ampliador de posts del blog.

Lo que se blinda es el contrato que hace que ampliar sea seguro: se AÑADE, nunca
se reescribe, y si el añadido no mejora la pieza se tira y se conserva el
original. Sin esa segunda mitad, un motor de ampliación acaba metiendo relleno
en todo lo que toca, que es justo lo que el gate de rigor existe para impedir.

El motor de las fichas de entidad (`scripts.seo.augment_deep`) ya tenía ese
contrato, pero atado a `SeoContent`: los posts del blog no podían pasar por él.
"""
from __future__ import annotations

import pytest

from app.services.editorial_review import EditorialVerdict
from scripts.blog import augment_posts as ap

CUERPO = "## Lo que ya decía\n\nUn cuerpo con hechos reales y comprobables.\n"


class _Entidad:
    slug = "extremoduro"
    name = "Extremoduro"


class _Ancla:
    entity_type = "artist"
    entity = _Entidad()
    name = "Extremoduro"


class _Post:
    id = 20
    kind = "evergreen"
    title = "Un post cualquiera"
    target_keyword = None
    excerpt = "Un resumen cualquiera."
    body_md = CUERPO


@pytest.fixture()
def motor(monkeypatch):
    """Cablea las piezas caras (dossier, LLM, rigor) y deja elegir qué devuelven."""
    estado = {"ancla": _Ancla(), "seccion": ("## Lo nuevo\n\nMaterial verificado.", "Lo nuevo"),
              "antes": 60, "despues": 80, "verdict": "pass"}

    monkeypatch.setattr(ap, "resolve_central_entity", lambda db, **kw: estado["ancla"])
    monkeypatch.setattr(ap, "gather_entity_dossier", lambda db, t, e: object())
    monkeypatch.setattr(ap, "_corpus_gap_section",
                        lambda *a, **kw: estado["seccion"])
    monkeypatch.setattr(ap, "normalize_headings", lambda b: b)
    monkeypatch.setattr(ap, "strip_ai_tells", lambda b: b)
    # OJO: en producción el enlazado SÍ toca el cuerpo entero (le mete enlaces
    # markdown), así que un mock identidad sería más permisivo que la realidad y
    # dejaría pasar un contrato que allí no se cumple. Se simula que modifica.
    monkeypatch.setattr(ap, "autolink_corpus",
                        lambda b, *a, **kw: b.replace("hechos", "[hechos](/x)"))

    def _review(body, *, kind, subject, allowed_terms=None, **kw):
        es_original = body.strip() == CUERPO.strip()
        score = estado["antes"] if es_original else estado["despues"]
        return EditorialVerdict(
            verdict="pass" if es_original else estado["verdict"], score=score,
        )

    monkeypatch.setattr(ap, "editorial_review", _review)
    return estado


def test_lo_que_ya_decia_no_se_pierde(motor):
    """El contrato entero: lo que ya decía sigue ahí y la pieza crece.

    No se exige el original LITERAL porque el enlazado interno reescribe menciones
    en enlaces; lo que no puede pasar es que desaparezca contenido ni que encoja.
    """
    res = ap.augmentar(None, None, _Post(), corpus_index=None, link_stats=None)
    assert res["noop"] is False
    assert "Lo que ya decía" in res["after"]                    # su encabezado sigue
    assert "comprobables" in res["after"]                       # y su prosa
    assert res["after"].index("Lo que ya decía") < res["after"].index("Lo nuevo")
    assert res["after_len"] > res["before_len"]                 # nunca encoge
    assert "Material verificado" in res["after"]                # y lo nuevo entró
    assert res["added"].startswith("## Lo nuevo")               # la sección, aparte


def test_si_no_mejora_se_tira_la_ampliacion(motor):
    """Un añadido que baja el rigor es relleno: se conserva el original."""
    motor["despues"] = 45   # peor que los 60 de partida
    res = ap.augmentar(None, None, _Post(), corpus_index=None, link_stats=None)
    assert res["noop"] is True
    assert "no mejora" in res["motivo"]


def test_un_rechazo_del_rigor_tambien_lo_tira(motor):
    motor["verdict"] = "reject"
    motor["despues"] = 90   # aunque puntúe alto, si lo rechaza no entra
    res = ap.augmentar(None, None, _Post(), corpus_index=None, link_stats=None)
    assert res["noop"] is True


def test_sin_material_en_el_corpus_no_se_inventa_nada(motor):
    motor["seccion"] = (None, None)
    res = ap.augmentar(None, None, _Post(), corpus_index=None, link_stats=None)
    assert res["noop"] is True
    assert res["motivo"] == "el corpus no da para más"


def test_sin_ancla_fiable_no_se_toca(motor):
    """`blog_anchor` es conservador: ante la duda devuelve None, y entonces no hay
    dossier del que tirar. Ampliar a ciegas sería inventar."""
    motor["ancla"] = None
    res = ap.augmentar(None, None, _Post(), corpus_index=None, link_stats=None)
    assert res["noop"] is True
    assert res["motivo"] == "sin ancla fiable"


def test_un_post_vacio_no_rompe(motor):
    p = _Post()
    p.body_md = "   "
    res = ap.augmentar(None, None, p, corpus_index=None, link_stats=None)
    assert res["noop"] is True
