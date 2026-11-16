"""Una noticia no se publica sin su artículo, ni afirmando lo que el artículo no dice.

Caso real: el post #65 («Flores Amarillas 2027», 12-10-2026) se redactó el 14-09
sin artículo y salió con un cartel inventado. Aquí se vigilan los tres frenos del
materializador:

  - sin artículo (ni texto pegado) → no hay post;
  - un borrador anterior a NEWS_GROUNDING_SINCE se reescribe con el artículo;
  - un nombre que el artículo no trae → revisión humana con el motivo, no publicación.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.tests.test_blog_backfill import _prop, db, gates  # noqa: F401  (fixtures)
from scripts.blog import materialize_proposals as mp

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "flores_amarillas_2027.json").read_text("utf-8")
)
POST_65 = FIXTURE["post_65"]
NUEVO = datetime(2026, 11, 1, tzinfo=UTC)


@pytest.fixture()
def material(monkeypatch, gates):  # noqa: F811
    """El artículo que se 'descarga' y las propuestas que se reescriben."""
    estado = {"articulo": POST_65["articulo"], "reescritas": [], "motivos": []}
    monkeypatch.setattr(mp, "_articulo_de_propuesta", lambda _db, _p: estado["articulo"])
    monkeypatch.setattr("app.services.source_grounding.nombres_de_casa",
                        lambda _db: {"plasencia", "kutxi romero", "marea"})
    # El juez contra el artículo: no encuentra nada (sin cita literal).
    monkeypatch.setattr("app.services.instagram.caption_guard._lo_dice_el_articulo",
                        lambda frase, material: {"verdict": "not_found"})

    def _a_revision(sesion, post, **kw):
        post.status = "pending_review"
        sesion.commit()
        gates["a_revision"].append(post.title)
        estado["motivos"].append((kw.get("blocked_by"), kw.get("reason")))

    monkeypatch.setattr(mp, "propose_for_review", _a_revision)
    return estado


def test_sin_articulo_no_hay_post(db, gates, material):  # noqa: F811
    material["articulo"] = ""
    p = _prop(db, "Flores Amarillas 2027", dias=0, kind="news", created_at=NUEVO,
              body_md=POST_65["body_md"])
    assert mp._materialize_one(db, p, mp.date.today()) == "discarded"
    assert p.status == "discarded"
    assert gates["publicados"] == [] and gates["a_revision"] == []
    assert any("sin artículo" in s for s, _ in gates["mails"])


def test_el_cartel_inventado_va_a_revision_con_su_motivo(db, gates, material):  # noqa: F811
    p = _prop(db, "Flores Amarillas 2027", dias=0, kind="news", created_at=NUEVO,
              body_md=POST_65["body_md"])
    assert mp._materialize_one(db, p, mp.date.today()) == "review"
    assert gates["publicados"] == []
    gate, motivo = material["motivos"][0]
    assert gate == "noticia"
    assert "Fito Cabrales" in motivo and "Kutxi Romero" in motivo


def test_un_borrador_de_antes_del_arreglo_se_reescribe(db, gates, material, monkeypatch):  # noqa: F811
    def _reescribe(**kw):
        material["reescritas"].append(kw["source_excerpt"])
        return {"title": "Flores Amarillas tendrá una segunda edición en Plasencia",
                "body_md": "La segunda edición se celebrará en Plasencia. " * 10,
                "excerpt": "", "meta_title": "", "meta_description": ""}

    monkeypatch.setattr("app.services.news_research.research_and_write", _reescribe)
    p = _prop(db, "Flores Amarillas 2027", dias=0, kind="news",
              created_at=datetime(2026, 9, 14, 9, 0), body_md=POST_65["body_md"])
    assert mp._materialize_one(db, p, mp.date.today()) == "published"
    assert material["reescritas"] == [POST_65["articulo"]]
    assert "Fito" not in p.body_md


def test_una_noticia_fiel_a_su_articulo_se_publica(db, gates, material, monkeypatch):  # noqa: F811
    material["articulo"] = FIXTURE["prop_539"]["articulo"]
    monkeypatch.setattr("app.services.instagram.caption_guard._lo_dice_el_articulo",
                        lambda frase, material: {"verdict": "supported"})
    p = _prop(db, "Flores Amarillas reunirá 20 grupos", dias=0, kind="news",
              created_at=NUEVO, body_md=FIXTURE["prop_539"]["body_md"])
    assert mp._materialize_one(db, p, mp.date.today()) == "published"
