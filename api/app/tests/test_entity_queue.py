"""Cola «Relaciones y entidades» del panel (plan de relaciones, 18-11-2026)."""
import pytest

from app.db.models import EntityProposal
from app.services import entity_queue as eq
from app.tests.test_admin_summary import db  # noqa: F401 — fixture SQLite con las tablas


def test_una_propuesta_se_aprueba_y_no_se_publica_sola(db):  # noqa: F811
    p = EntityProposal(clave="qid:Q329984", tipo="Place", nombre="Úbeda", qid="Q329984",
                       relaciones=[{"desde": "person:joaquin-sabina", "predicado": "birthPlace"}])
    db.add(p)
    db.commit()
    assert eq.decidir_propuesta(db, p.id, "aprobar")["estado"] == "aprobada"
    with pytest.raises(eq.AccionNoValida):
        eq.decidir_propuesta(db, p.id, "aprobar")
    lista = eq.listar(db)
    assert lista["cuenta"]["aprobada"] == 1
    assert lista["propuestas"]["aprobada"][0]["nombre"] == "Úbeda"


def test_descartar_y_recuperar(db):  # noqa: F811
    p = EntityProposal(clave="qid:Q1", tipo="Person", nombre="Alguien", relaciones=[])
    db.add(p)
    db.commit()
    eq.decidir_propuesta(db, p.id, "descartar")
    assert eq.decidir_propuesta(db, p.id, "recuperar")["estado"] == "propuesta"


def test_propuesta_desconocida(db):  # noqa: F811
    with pytest.raises(LookupError):
        eq.decidir_propuesta(db, 999, "aprobar")
