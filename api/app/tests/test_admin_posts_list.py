"""Tests del listado de entradas que alimenta el panel del blog.

Blindan dos cosas que se vieron con datos de producción el 21-09-2026:

1. El panel solo pedía `pending_review`, así que 11 entradas programadas hasta
   diciembre y 4 rechazadas no se veían en NINGUNA pantalla. Ahora pide
   `?status=all` y agrupa; si ese filtro dejara de devolver todos los estados,
   el contenido volvería a ser invisible sin que nada avisara.

2. Los días de espera se calculaban en el frontend contra un `30` escrito a mano
   en TypeScript, mientras el correo diario usaba el suyo en Python. Aquí se
   comprueba que el número sale de `REVIEW_ROT_DAYS` y no de una copia.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import JSON, MetaData, Text, create_engine
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Session

from app.db.models import Post, User
from app.routers.admin import _post_to_item, admin_posts_list
from app.services.publishing import REVIEW_ROT_DAYS

AHORA = datetime.now(UTC)


@pytest.fixture()
def db():
    """SQLite en memoria con las tablas del blog (tipos Postgres traducidos)."""
    md = MetaData()
    for modelo in (User, Post):
        t = modelo.__table__.to_metadata(md)
        for col in t.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()
            elif isinstance(col.type, TSVECTOR):
                col.type = Text()
            sd = col.server_default
            if sd is not None and "::" in str(getattr(sd, "arg", "")):
                col.server_default = None
        t.indexes.clear()
    engine = create_engine("sqlite://")
    md.create_all(engine)
    with Session(engine) as s:
        yield s


def _post(db, titulo, *, estado, dias=0, programado=None) -> Post:
    p = Post(
        slug=titulo.lower().replace(" ", "-"), kind="evergreen", status=estado,
        title=titulo, body_md="Un cuerpo cualquiera.",
        created_at=AHORA - timedelta(days=dias), scheduled_for=programado,
    )
    db.add(p)
    db.commit()
    return p


# --- Días de espera --------------------------------------------------------- #
def test_una_entrada_recien_creada_no_esta_podrida(db):
    item = _post_to_item(_post(db, "Recién hecha", estado="pending_review", dias=0))
    assert item.days_waiting == 0
    assert item.stale is False


def test_el_umbral_de_podredumbre_sale_de_la_constante(db):
    """Justo por debajo y justo por encima: si alguien mueve `REVIEW_ROT_DAYS`,
    el panel y el correo se mueven con él en vez de discrepar en silencio."""
    justo_antes = _post_to_item(
        _post(db, "Casi", estado="pending_review", dias=REVIEW_ROT_DAYS - 1)
    )
    justo_despues = _post_to_item(
        _post(db, "Pasada", estado="pending_review", dias=REVIEW_ROT_DAYS)
    )
    assert justo_antes.stale is False
    assert justo_despues.stale is True
    assert justo_despues.days_waiting == REVIEW_ROT_DAYS


def test_los_dias_solo_cuentan_mientras_espera_decision(db):
    """En una publicada medirían su antigüedad, que no es una tarea pendiente."""
    publicada = _post_to_item(
        _post(db, "Ya salió", estado="published", dias=400)
    )
    assert publicada.days_waiting == 0
    assert publicada.stale is False


# --- Filtro de estados ------------------------------------------------------ #
def test_status_all_devuelve_todos_los_estados(db):
    """Lo que hacía invisibles 11 entradas programadas y 4 rechazadas."""
    for estado in ("pending_review", "scheduled", "approved", "draft",
                   "rejected", "published"):
        _post(db, f"Entrada {estado}", estado=estado)

    todos = admin_posts_list(status="all", db=db, _admin=None)

    assert {i.status for i in todos} == {
        "pending_review", "scheduled", "approved", "draft", "rejected", "published",
    }


def test_sin_status_tambien_vienen_todos(db):
    _post(db, "Una", estado="pending_review")
    _post(db, "Otra", estado="rejected")
    assert len(admin_posts_list(status=None, db=db, _admin=None)) == 2


def test_el_filtro_por_estado_sigue_filtrando(db):
    _post(db, "Espera", estado="pending_review")
    _post(db, "Programada", estado="scheduled")

    solo_pendientes = admin_posts_list(status="pending_review", db=db, _admin=None)

    assert [i.title for i in solo_pendientes] == ["Espera"]


# --- La fecha viaja siempre ------------------------------------------------- #
def test_la_fecha_de_programacion_viaja_en_la_respuesta(db):
    """Las seis respuestas que devuelven un post pasan por el mismo helper: antes
    solo la de listar mandaba `scheduled_for`, así que una entrada programada
    perdía su fecha en cuanto se tocaba desde el panel."""
    cuando = AHORA + timedelta(days=7)
    item = _post_to_item(
        _post(db, "Con fecha", estado="scheduled", programado=cuando)
    )
    assert item.scheduled_for is not None


# --- Despublicar --------------------------------------------------------- #
def test_despublicar_le_dice_a_next_que_lo_olvide(db, monkeypatch):
    """Sin revalidar, la entrada seguía viéndose en /blog hasta diez minutos
    después de quitarla, así que el botón parecía no hacer nada. Publicar ya
    revalidaba; el camino contrario se había quedado sin ello."""
    from app.routers import admin as router

    revalidadas: list[str] = []
    monkeypatch.setattr("app.services.publishing._revalidate_next", revalidadas.append)

    p = _post(db, "Ya no la quiero", estado="published")
    router.admin_post_unpublish(post_id=p.id, db=db, _admin=None)

    assert p.status == "approved"
    assert revalidadas == [p.slug]
