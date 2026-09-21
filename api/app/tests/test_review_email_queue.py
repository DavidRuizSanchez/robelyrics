"""Tests del correo de «entradas para revisar».

El fallo que blindan se vio con datos de prod el 05-09-2026: había 24 posts en
`pending_review`, algunos desde el 19 de mayo, y el usuario no sabía ni que
existían. El correo pedía los pendientes con `order_by(created_at.desc())` y
`limit(10)`, así que en cuanto la cola pasó de diez, los del fondo dejaron de
aparecer en NINGÚN correo: solo eran alcanzables entrando al panel y bajando
hasta el final de la página. Un embudo que se atasca solo.

Ahora salen primero los que llevan más esperando, el post que dispara el aviso
va el primero de todos (es la novedad), y lo que no cabe se nombra al pie en vez
de desaparecer en silencio.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import JSON, MetaData, Text, create_engine
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Session

from app.db.models import Post, User
from app.services import publishing

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


@pytest.fixture()
def correo(monkeypatch):
    """Intercepta el correo y devuelve lo que se le pasó al render."""
    capturado: dict = {}

    def _render(items, panel_url, nota_final=""):
        capturado["titulos"] = [i["title"] for i in items]
        capturado["nota"] = nota_final
        return "<html>", "texto"

    def _send(**kw):
        capturado["asunto"] = kw.get("subject")

    monkeypatch.setenv("ADMIN_EMAIL", "david@ejemplo.tld")
    # Imports locales de la función: se parchean en su módulo de origen.
    monkeypatch.setattr("app.services.auth.create_admin_action_token",
                        lambda pid, action: f"tok-{pid}-{action}")
    monkeypatch.setattr("app.services.email.render_admin_review_email", _render)
    monkeypatch.setattr("app.services.email.send_email", _send)
    return capturado


def _post(db, titulo, *, dias_de_antiguedad) -> Post:
    p = Post(
        slug=titulo.lower().replace(" ", "-"), kind="evergreen",
        status="pending_review", title=titulo, body_md="Un cuerpo cualquiera.",
        created_at=AHORA - timedelta(days=dias_de_antiguedad), entities=[],
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_los_mas_antiguos_no_se_quedan_fuera(db, correo):
    """Con la cola llena, el correo tiene que llegar a los del fondo."""
    for i in range(20):
        _post(db, f"Viejo {i:02d}", dias_de_antiguedad=100 - i)
    nuevo = _post(db, "El de hoy", dias_de_antiguedad=0)

    publishing._notify_admin_review(db, nuevo)

    titulos = correo["titulos"]
    assert titulos[0] == "El de hoy"          # la novedad, primero
    assert titulos[1] == "Viejo 00"           # y detrás, el que más lleva esperando
    assert len(titulos) == publishing.MAX_REVIEW_EMAIL_ITEMS
    # Lo que no cabe se dice, no se esconde.
    assert f"{21 - publishing.MAX_REVIEW_EMAIL_ITEMS} más" in correo["nota"]


def test_el_asunto_cuenta_la_cola_entera(db, correo):
    for i in range(20):
        _post(db, f"Viejo {i:02d}", dias_de_antiguedad=100 - i)
    nuevo = _post(db, "El de hoy", dias_de_antiguedad=0)

    publishing._notify_admin_review(db, nuevo)

    assert "21 entradas" in correo["asunto"]


def test_sin_recorte_no_hay_nota(db, correo):
    nuevo = _post(db, "El de hoy", dias_de_antiguedad=0)
    _post(db, "Otro", dias_de_antiguedad=3)

    publishing._notify_admin_review(db, nuevo)

    assert correo["titulos"] == ["El de hoy", "Otro"]
    assert correo["nota"] == ""


def test_solo_entran_los_pendientes(db, correo):
    """Lo publicado o rechazado no vuelve al correo."""
    nuevo = _post(db, "El de hoy", dias_de_antiguedad=0)
    ya = _post(db, "Ya publicado", dias_de_antiguedad=5)
    ya.status = "published"
    db.commit()

    publishing._notify_admin_review(db, nuevo)

    assert correo["titulos"] == ["El de hoy"]


# --------------------------------------------------------------------------- #
# El aviso de LOTE: sin post que lo dispare
# --------------------------------------------------------------------------- #
def test_el_aviso_de_lote_no_necesita_un_post_concreto(db, correo):
    """Los scripts que crean varios de golpe (giras, mínimo semanal) avisan UNA
    vez al terminar: el correo ya es consolidado, así que uno por pieza serían
    ocho correos casi idénticos. Sin disparador, manda la antigüedad."""
    _post(db, "El más viejo", dias_de_antiguedad=90)
    _post(db, "El de en medio", dias_de_antiguedad=30)
    _post(db, "El más nuevo", dias_de_antiguedad=1)

    publishing.notify_review_queue(db)

    assert correo["titulos"] == ["El más viejo", "El de en medio", "El más nuevo"]


def test_sin_nada_pendiente_no_se_manda_nada(db, correo):
    publishing.notify_review_queue(db)
    assert "titulos" not in correo


def test_proponer_para_revision_borra_la_fecha_de_programacion(db, monkeypatch):
    """Una entrada que vuelve a revisión no conserva su antigua fecha.

    Se vio en producción el 21-09-2026: la entrada #51 estaba en `pending_review`
    con `scheduled_for` del 16 de septiembre, ya pasado. Esa fecha no publica nada
    (`flush_scheduled_due` solo mira las `scheduled`), pero el panel la pintaba
    como «programado el 16 de sep», así que parecía que iba a salir sola. El
    desprogramado manual ya limpiaba el campo; este camino se había quedado atrás.
    """
    # El autolink del corpus consulta el catálogo entero, que esta fixture no
    # monta: aquí lo que se prueba es el estado, no el enlazado.
    monkeypatch.setattr("app.services.entity_resolver.build_corpus_index",
                        lambda _db: {})
    monkeypatch.setattr("app.services.url_resolver.guard_internal_links",
                        lambda _db, body: SimpleNamespace(changed=False, body_md=body))

    p = _post(db, "Volvió de la cola", dias_de_antiguedad=3)
    p.status = "scheduled"
    p.scheduled_for = AHORA - timedelta(days=5)
    db.commit()

    publishing.propose_for_review(db, p, notify=False)

    assert p.status == "pending_review"
    assert p.scheduled_for is None
