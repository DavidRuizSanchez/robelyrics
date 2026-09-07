"""Tests de la REPESCA del hueco diario del blog.

El fallo que blindan pasó en prod el 05-09-2026: el gate de rigor descartó el
post programado para ese día («El universo de Albert Pla») y, como el cron no
tenía plan B, el blog no publicó nada. La propuesta moría con un `continue` y
ahí se acababa el día.

Ahora, cuando lo programado para hoy muere del todo, se adelanta la siguiente
propuesta ADELANTABLE de la cola. Lo que se vigila aquí es lo que puede volver a
romperse:

  - que una EFEMÉRIDE no se adelante nunca (su día es su día),
  - que el tope de intentos exista de verdad (cada intento fallido descarta su
    propuesta: sin tope, un día con el juez duro vacía la cola),
  - que un post esperando aprobación NO dispare repesca (saldrían dos),
  - y que un segundo pase del cron no publique encima de lo ya publicado.

Son también los primeros tests de la cascada de `materialize_proposals`, que no
tenía ninguno.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import JSON, MetaData, Text, create_engine
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Session

from app.db.models import ContentProposal, Post, User
from app.services.editorial_review import EditorialVerdict
from app.services.fact_check import FactCheckReport
from app.services.focus_check import FocusReport
from app.services.lyric_guard import LyricGuardReport
from app.services.publishing import backfill_candidates
from scripts.blog import materialize_proposals as mp

HOY = date.today()


@pytest.fixture()
def db():
    """SQLite en memoria con las tablas del blog.

    Tres cosas de Postgres no viajan y hay que traducirlas: `JSONB` y `TSVECTOR`
    (que el compilador de SQLite no sabe renderizar) y los `server_default` con
    cast (`'[]'::jsonb`), que no parsea. El default de Python (`default=list`)
    sigue haciendo su trabajo. `User` entra porque `posts.approved_by` la
    referencia.
    """
    md = MetaData()
    for modelo in (User, Post, ContentProposal):
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


def _prop(db, titulo, *, dias, kind="evergreen", status="scheduled", **kw) -> ContentProposal:
    """Una propuesta programada dentro de `dias` (negativo = ya vencida)."""
    base = dict(
        kind=kind, title=titulo, status=status,
        scheduled_for=HOY + timedelta(days=dias),
        body_md="Un cuerpo con hechos de sobra." * 40,
        quality_tier="cornerstone", engagement_score=70,
        entities=[], keywords=[],
    )
    base.update(kw)
    p = ContentProposal(**base)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture()
def gates(monkeypatch):
    """Neutraliza los gates caros (todos van contra gpt-4o o la web) y registra
    lo que pasó. `rigor` decide por TÍTULO qué se rechaza."""
    estado: dict = {
        "rigor": {},            # título → "reject" | "pass"
        "rigor_default": "pass",
        "juzgados": [],         # títulos que pasaron por el gate de rigor, en orden
        "publicados": [],
        "a_revision": [],
        "mails": [],
    }

    def _rigor(body_md, *, kind, subject, event_when=None, **kw):  # noqa: ARG001
        estado["juzgados"].append(subject)
        if estado["rigor"].get(subject, estado["rigor_default"]) == "reject":
            return EditorialVerdict(verdict="reject", score=20, reasons=["genérica; sin datos"])
        return EditorialVerdict(verdict="pass", score=90)

    def _publicar(db, post, **kw):  # noqa: ARG001
        post.status = "published"
        db.commit()
        estado["publicados"].append(post.title)

    def _a_revision(db, post, **kw):  # noqa: ARG001
        post.status = "pending_review"
        db.commit()
        estado["a_revision"].append(post.title)

    monkeypatch.setattr(mp, "editorial_review", _rigor)
    monkeypatch.setattr(mp, "check_focus", lambda body, subject, focus="":
                        FocusReport(ok=True, score=95, drift_headings=[], trimmed_body_md=None))
    monkeypatch.setattr(mp, "check_body", lambda db, body, use_web=False: FactCheckReport())
    monkeypatch.setattr(mp, "auto_publish_post", _publicar)
    monkeypatch.setattr(mp, "propose_for_review", _a_revision)
    monkeypatch.setattr(mp, "_notify_admin", lambda s, t: estado["mails"].append((s, t)))
    monkeypatch.setattr(mp, "generate_proposal_draft", lambda db, p: False)
    # Estos dos se importan DENTRO de la función, así que se parchean en su
    # módulo de origen: en `mp` ni siquiera existe el nombre.
    monkeypatch.setattr("app.services.lyric_guard.check_lyrics",
                        lambda db, body: LyricGuardReport())
    monkeypatch.setattr("app.services.text_sanitizer.embed_youtube_links", lambda body: body)
    return estado


# --------------------------------------------------------------------------- #
# El selector: qué se puede adelantar y qué no
# --------------------------------------------------------------------------- #
def test_una_efemeride_no_se_adelanta_jamas(db):
    """Su día es su día: un aniversario publicado otro día no es un aniversario."""
    _prop(db, "40 años de Rock transgresivo", dias=3, kind="album-anniversary")
    _prop(db, "Cumpleaños", dias=5, kind="anniversary")
    assert backfill_candidates(db, HOY) == []


def test_lo_que_tiene_fecha_atada_queda_fuera(db):
    """Evento, fecha sugerida propia, sin borrador o ya vencida: ninguna vale."""
    _prop(db, "Concierto en Cáceres", dias=4, kind="news", event_date=HOY + timedelta(days=10))
    _prop(db, "Con fecha sugerida", dias=4, recommended_date=HOY + timedelta(days=4))
    _prop(db, "Sin borrador", dias=4, body_md=None)
    _prop(db, "Ya vencida", dias=-1)
    _prop(db, "Aún sin programar", dias=4, status="approved")
    assert backfill_candidates(db, HOY) == []


def test_se_coge_la_mas_proxima_primero(db):
    """Se roba el hueco que menos futuro rompe."""
    _prop(db, "Dentro de tres semanas", dias=21)
    _prop(db, "La semana que viene", dias=7)
    _prop(db, "Pasado mañana", dias=2)
    assert [c.title for c in backfill_candidates(db, HOY)] == [
        "Pasado mañana", "La semana que viene", "Dentro de tres semanas",
    ]


def test_el_tope_limita_los_candidatos(db):
    for i in range(6):
        _prop(db, f"Sub {i}", dias=i + 1)
    assert len(backfill_candidates(db, HOY, limit=mp.BACKFILL_MAX)) == mp.BACKFILL_MAX


# --------------------------------------------------------------------------- #
# La repesca
# --------------------------------------------------------------------------- #
def test_el_hueco_se_cubre_con_el_siguiente(db, gates):
    """EL CASO DE ALBERT PLA: si el rigor tumba el post del día, sale el siguiente."""
    caido = _prop(db, "Albert Pla", dias=0)
    recambio = _prop(db, "Rosendo", dias=7)
    gates["rigor"]["Albert Pla"] = "reject"

    mp.run(db, HOY)

    assert gates["publicados"] == ["Rosendo"]
    assert caido.status == "discarded"
    assert recambio.status == "used"
    # El adelanto queda registrado: salió HOY, no el día que le tocaba.
    assert recambio.scheduled_for == HOY
    asunto, cuerpo = gates["mails"][-1]
    assert asunto.startswith("✅")
    assert "Rosendo" in cuerpo and "Albert Pla" in cuerpo


def test_sin_recambio_el_dia_se_queda_sin_post_y_se_avisa(db, gates):
    """Solo hay efemérides por delante: no se toca ninguna y se avisa."""
    _prop(db, "Albert Pla", dias=0)
    efemeride = _prop(db, "40 años", dias=3, kind="album-anniversary")
    gates["rigor_default"] = "reject"

    mp.run(db, HOY)

    assert gates["publicados"] == []
    assert gates["juzgados"] == ["Albert Pla"]  # no se juzgó nada más
    assert efemeride.status == "scheduled"
    assert efemeride.scheduled_for == HOY + timedelta(days=3)  # intacta
    assert gates["mails"][-1][0].startswith("⚠️")


def test_la_cascada_de_descartes_tiene_tope(db, gates):
    """Cada intento fallido descarta: sin tope, un día malo vacía la cola."""
    _prop(db, "Albert Pla", dias=0)
    subs = [_prop(db, f"Sub {i}", dias=i + 1) for i in range(5)]
    gates["rigor_default"] = "reject"

    mp.run(db, HOY)

    # El del día + exactamente BACKFILL_MAX recambios.
    assert len(gates["juzgados"]) == 1 + mp.BACKFILL_MAX
    assert gates["publicados"] == []
    intactos = [s for s in subs if s.status == "scheduled"]
    assert len(intactos) == len(subs) - mp.BACKFILL_MAX
    assert gates["mails"][-1][0].startswith("⚠️")


def test_un_post_a_revision_no_dispara_repesca(db, gates, monkeypatch):
    """El post existe y está a un clic del admin: adelantar otro publicaría dos."""

    class _CitaEnZonaGris:
        quote = "un verso dudoso"
        reason = "coincidencia parcial"

    class _Reporte:
        blocking: list = []
        to_review = [_CitaEnZonaGris()]

    monkeypatch.setattr("app.services.lyric_guard.check_lyrics", lambda db, body: _Reporte())
    _prop(db, "Albert Pla", dias=0)
    recambio = _prop(db, "Rosendo", dias=7)

    mp.run(db, HOY)

    assert gates["a_revision"] == ["Albert Pla"]
    assert gates["publicados"] == []
    assert recambio.status == "scheduled"
    assert recambio.scheduled_for == HOY + timedelta(days=7)


def test_no_se_publica_encima_de_lo_ya_publicado_hoy(db, gates):
    """Idempotencia: si hoy ya salió algo (efeméride u otra pasada del cron), no
    se repesca. Si no, un segundo pase pondría un segundo post."""
    from datetime import UTC, datetime

    db.add(Post(slug="ya-salio", kind="anniversary", status="published",
                title="Ya salió", body_md="Ya publicado hoy por el cron de efemérides.",
                published_at=datetime.now(UTC), entities=[]))
    db.commit()
    _prop(db, "Albert Pla", dias=0)
    recambio = _prop(db, "Rosendo", dias=7)
    gates["rigor"]["Albert Pla"] = "reject"

    resultado = mp.run(db, HOY)

    assert resultado["repesca"] == "ya_publicado"
    assert gates["publicados"] == []
    assert recambio.status == "scheduled"


def test_dry_run_no_toca_nada(db, gates):
    caido = _prop(db, "Albert Pla", dias=0)
    recambio = _prop(db, "Rosendo", dias=7)
    gates["rigor_default"] = "reject"

    mp.run(db, HOY, dry_run=True)

    assert gates["juzgados"] == []
    assert gates["publicados"] == []
    assert caido.status == "scheduled"
    assert recambio.scheduled_for == HOY + timedelta(days=7)


def test_no_backfill_deja_el_comportamiento_viejo(db, gates):
    _prop(db, "Albert Pla", dias=0)
    recambio = _prop(db, "Rosendo", dias=7)
    gates["rigor_default"] = "reject"

    mp.run(db, HOY, backfill=False)

    assert gates["publicados"] == []
    assert recambio.status == "scheduled"


# --------------------------------------------------------------------------- #
# La cascada base, que tampoco tenía tests
# --------------------------------------------------------------------------- #
def test_lo_limpio_se_publica(db, gates):
    p = _prop(db, "Albert Pla", dias=0)
    assert mp.run(db, HOY)["cubierto"] is True
    assert gates["publicados"] == ["Albert Pla"]
    assert p.status == "used"


def test_el_rigor_descarta_y_no_publica(db, gates):
    p = _prop(db, "Albert Pla", dias=0)
    gates["rigor_default"] = "reject"
    mp.run(db, HOY)
    assert gates["publicados"] == []
    assert p.status == "discarded"
