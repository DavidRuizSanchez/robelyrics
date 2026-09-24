"""Un gate que retiene una pieza no puede mandar el correo que pide aprobarla.

El bucle, medido en producción el 24-09-2026: llega «Una entrada para revisar»
con su botón APROBAR → el botón llama a `auto_publish_post` → un gate la retiene
→ `propose_for_review` se llamaba con el `notify=True` por defecto → sale un
correo idéntico en el acto. Clic, pantalla roja, correo nuevo. Sin fin.

Estos tests NO parchean `propose_for_review` —es justo la función por la que pasa
el fallo—; el corte va en `send_email`, que es la frontera real. Un mock más
permisivo que la realidad no prueba el camino que dice probar.
"""
from __future__ import annotations

import inspect

import pytest
from sqlalchemy import JSON, MetaData, Text, create_engine
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Session

from app.db.models import Post, User
from app.services import lyric_guard as lg
from app.services import publishing

# Letra real, para que el verso inventado del test lo sea de verdad.
SO_PAYASO = (
    "Quiero ser tu perro fiel, tu esclavo sin rechistar\n"
    "So payaso y me tiemblan los pies a su lado\n"
)


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
def correos(monkeypatch):
    """Cuenta los correos que SALEN. Lo demás del camino se aparta, pero los dos
    gates y `propose_for_review` corren de verdad."""
    enviados: list[dict] = []
    monkeypatch.setenv("ADMIN_EMAIL", "david@ejemplo.tld")
    monkeypatch.setattr("app.services.email.send_email",
                        lambda **kw: enviados.append(kw))
    # Enlazado interno y revalidación: ruido para lo que se está probando.
    monkeypatch.setattr("app.services.entity_resolver.build_corpus_index",
                        lambda db: {})
    monkeypatch.setattr("app.services.entity_resolver.load_link_stats", lambda: {})
    monkeypatch.setattr("app.services.entity_resolver.autolink_corpus",
                        lambda body, idx, **kw: body)
    monkeypatch.setattr("app.services.text_sanitizer.normalize_headings",
                        lambda body: body)
    monkeypatch.setattr(
        "app.services.url_resolver.guard_internal_links",
        lambda db, body: type("R", (), {"changed": False, "body_md": body,
                                        "summary": lambda self: ""})(),
    )
    monkeypatch.setattr(publishing, "_revalidate_next", lambda slug: None)
    return enviados


@pytest.fixture()
def corpus(monkeypatch):
    monkeypatch.setattr(lg, "_load_songs", lambda db: [
        lg._SongLyrics("So Payaso", "Agila", 1996, lg.normalize(SO_PAYASO), True),
    ])
    monkeypatch.setattr(lg, "_external_verses", lambda: [])


def _post(db, cuerpo: str) -> Post:
    p = Post(slug="una-entrada", kind="evergreen", status="pending_review",
             title="Una entrada", body_md=cuerpo, entities=[])
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_un_verso_inventado_retiene_la_pieza_y_no_manda_correo(db, correos, corpus):
    """El corazón del bucle: retener no puede pedir que aprueben lo retenido."""
    post = _post(db, 'En "So Payaso" canta: "Me subo a un tren que va a ninguna parte".')

    resultado = publishing.auto_publish_post(db, post, factcheck=False, rigor=False)

    assert resultado["action"] == "pending_review"
    assert post.status == "pending_review"
    assert correos == []                      # ni uno


def test_el_motivo_dice_que_verso_y_de_que_cancion(db, correos, corpus):
    """El 409 se construye con esto. Antes el motivo solo vivía en el log."""
    post = _post(db, 'En "So Payaso" canta: "Me subo a un tren que va a ninguna parte".')

    resultado = publishing.auto_publish_post(db, post, factcheck=False, rigor=False)

    assert resultado["blocked_by"] == "lyrics"
    assert "Me subo a un tren" in resultado["reason"]
    assert "So Payaso" in resultado["reason"]
    # Y queda escrito, para que el correo pueda marcar la pieza.
    assert post.review_blocked_at is not None
    assert "Me subo a un tren" in post.review_blocked_reason


def test_aprobar_dos_veces_lo_retenido_sigue_sin_mandar_correo(db, correos, corpus):
    """La formulación literal de lo que le pasaba a David: clic, clic, clic."""
    post = _post(db, 'En "So Payaso" canta: "Me subo a un tren que va a ninguna parte".')

    for _ in range(3):
        publishing.auto_publish_post(db, post, factcheck=False, rigor=False)

    assert correos == []


def test_un_verso_real_no_retiene_nada(db, correos, corpus):
    """El otro lado del equilibrio: si la cita es buena, la pieza sale."""
    post = _post(db, 'En "So Payaso" canta: "So payaso y me tiemblan los pies a su lado".')

    resultado = publishing.auto_publish_post(db, post, factcheck=False, rigor=False)

    assert resultado["action"] == "published"
    assert post.review_blocked_reason is None


def test_los_tres_gates_enrutan_con_notify_false():
    """Estructural y barato: que nadie reintroduzca el bucle por copiar-pegar."""
    fuente = inspect.getsource(publishing.auto_publish_post)
    assert fuente.count("propose_for_review(db, post, notify=False") == 3
    # Ni una sola llamada que se deje el flag y vuelva a avisar desde aquí.
    assert "propose_for_review(db, post)" not in fuente


# --- El correo de una pieza retenida ----------------------------------------- #
def _item(**kw):
    base = {
        "title": "Una entrada", "kind_label": "Spotlight", "excerpt": "Un resumen.",
        "approve_url": "https://x.tld/aprobar-token", "reject_url": "https://x.tld/rechazar",
        "admin_url": "https://x.tld/biblioteca/admin/posts/59",
    }
    base.update(kw)
    return base


def test_una_pieza_retenida_no_ofrece_el_boton_de_aprobar():
    """Ese botón vuelve al tronco de publicación y se encuentra el mismo gate:
    ofrecerlo es pedir un clic que no puede funcionar."""
    from app.services.email import render_admin_review_email

    html, texto = render_admin_review_email(
        [_item(blocked_reason="el verso «Me subo a un tren» no está en el corpus")],
        "https://x.tld/panel",
    )

    assert "aprobar-token" not in html
    assert "aprobar-token" not in texto
    assert "Me subo a un tren" in html          # el motivo, a la vista
    assert "corregir" in html.lower()


def test_una_pieza_normal_conserva_su_boton():
    """El otro lado: sin bloqueo, el one-click sigue igual que siempre."""
    from app.services.email import render_admin_review_email

    html, texto = render_admin_review_email([_item()], "https://x.tld/panel")

    assert "aprobar-token" in html
    assert "aprobar-token" in texto
    assert "RETENIDA" not in html
