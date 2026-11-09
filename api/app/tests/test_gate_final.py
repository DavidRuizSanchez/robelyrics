"""El gate final: nada sale a Instagram con texto del proceso o metatexto.

Los captions del fixture son REALES (volcados de prod el 09-11-2026):
- `deben_bloquear`: los 11 que se publicaron (o iban a publicarse, #516) con
  notas internas, el proceso parafraseado o «el material disponible no…».
- `deben_pasar`: posts buenos, incluidos los que una búsqueda por PALABRA tumbaba
  (#402 «errores» es un título de canción, #408 «no consta» es del estudio,
  #463 «antiterrorista»).

Si una regla nueva bloquea uno de los buenos, la regla está mal, no el texto.
"""
from __future__ import annotations

import json
from datetime import UTC, date
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.models import InstagramQueueItem, InstagramQueueMedia, VideoClip
from app.services.instagram import gate_final, publisher

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "gate_final_captions.json").read_text("utf-8")
)


@pytest.mark.parametrize("item_id", sorted(FIXTURE["deben_bloquear"]))
def test_los_captions_malos_publicados_se_bloquean(item_id):
    v = gate_final.revisar(caption=FIXTURE["deben_bloquear"][item_id])
    assert not v.ok, f"#{item_id} habría vuelto a salir publicado"


@pytest.mark.parametrize("item_id", sorted(FIXTURE["deben_pasar"]))
def test_los_captions_buenos_pasan(item_id):
    v = gate_final.revisar(caption=FIXTURE["deben_pasar"][item_id])
    assert v.ok, f"falso positivo en #{item_id}: {v.motivo}"


def test_todo_en_minusculas_no_es_una_marca_de_trabajo():
    """La primera calibración tumbó 70 captions por «todo el universo de Robe»."""
    assert gate_final.revisar(caption="Esto y todo el universo Extremoduro.").ok
    assert not gate_final.revisar(caption="TODO: poner la fecha").ok


def test_el_interprete_sale_del_video_no_de_la_cancion():
    assert gate_final.interprete_del_video("Robe - Vigo 2024.11.09 (concierto completo)") == "Robe"
    assert gate_final.interprete_del_video(
        "EXTREMODURO EN DIRECTO  La Cubierta (Leganés) 1999") == "Extremoduro"
    assert gate_final.interprete_del_video(
        'ROBE "Concierto Completo/Full Concert" LA MAGDALENA SANTANDER 20.07.24 '
        "#robe #extremoduro") == "Robe"
    assert gate_final.interprete_del_video("Robe y Extremoduro, recopilatorio") is None


def test_el_caso_504_entero():
    """«El solo de «La Carrera»» en un concierto de Robe, era «Destrozares»."""
    caption = FIXTURE["deben_bloquear"]["504"]
    problemas = gate_final.problemas_de_clip(
        caption,
        interprete="Robe",
        titulos_permitidos={"Destrozares", "Destrozares, canciones para el final de los tiempos"},
        titulos_catalogo={"La Carrera", "Agila", "Destrozares"},
    )
    texto = " ".join(problemas)
    assert "atribuye a Extremoduro un concierto de Robe" in texto
    assert "«La Carrera»" in texto
    assert "«Agila»" in texto


def test_el_verso_y_su_cancion_si_estan_permitidos():
    caption = ("El estribillo de «Destrozares» — Vigo\n\n🎵 «Y no lo siento»\n"
               "   — Robe, «Destrozares» (2023)")
    assert gate_final.problemas_de_clip(
        caption, interprete="Robe", titulos_permitidos={"Destrozares"},
        titulos_catalogo={"Destrozares", "La Carrera"},
    ) == []


# --- La cola: lo retenido no sale solo ----------------------------------------------

@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    InstagramQueueItem.__table__.create(engine)
    InstagramQueueMedia.__table__.create(engine)
    VideoClip.__table__.create(engine)
    with Session(engine) as s:
        yield s


def _item(db, **kw) -> InstagramQueueItem:
    base = dict(
        day=date.today(), slot=1, position=1, content_type="quote",
        title="Un verso", status="prepared", attempts=0, media_type="IMAGE",
        media_locked=False, image_url="https://res.cloudinary.com/x.jpg",
        caption="Un caption limpio.",
    )
    base.update(kw)
    it = InstagramQueueItem(**base)
    db.add(it)
    db.commit()
    db.refresh(it)
    return it


def test_un_item_retenido_no_lo_elige_el_goteo(db):
    _item(db, position=1, needs_human=True)
    siguiente = _item(db, position=2)
    assert publisher.next_pending(db).id == siguiente.id


def test_un_item_retenido_no_vence_aunque_este_programado(db):
    from datetime import datetime, timedelta

    _item(db, needs_human=True,
          publish_at=datetime.now(UTC) - timedelta(hours=1))
    assert publisher.due_pinned(db) == []


def test_publish_retiene_sin_llamar_a_meta_ni_gastar_intento(db, monkeypatch):
    def _no_toques_meta(*a, **k):
        raise AssertionError("con el texto retenido no se habla con Meta")

    monkeypatch.setattr(publisher.graph_api, "connection_is_healthy", _no_toques_meta)
    it = _item(db, caption=FIXTURE["deben_bloquear"]["487"])
    publisher.publish(db, it)
    db.refresh(it)
    assert it.needs_human is True
    # NO `failed`: el cortacircuitos cuenta los `failed` como señal de bloqueo
    # de Meta, y tres retenidos seguidos pararían la cola acusando a Meta.
    assert it.status == "prepared"
    assert it.attempts == 0
    assert it.error.startswith("Retenido antes de publicar")


def test_el_ensayo_tambien_retiene(db):
    it = _item(db, caption=FIXTURE["deben_bloquear"]["472"])
    publisher.publish(db, it, dry_run=True)
    db.refresh(it)
    assert it.needs_human is True


def test_un_clip_sin_texto_que_pase_no_cae_a_sus_notas(monkeypatch):
    """Antes, si el redactor no pasaba las guardas, se publicaba `texto_base`,
    que en un clip eran las notas del selector: así salió el #487."""
    from app.services.instagram import material as material_ig
    from app.services.instagram import newsroom

    class _Mat:
        prompt = "datos del clip"
        verificable = "datos del clip"

        def __bool__(self):
            return True

    monkeypatch.setattr(material_ig, "reunir", lambda db, topic: _Mat())

    def _rechaza(*a, **k):
        raise newsroom.TextoNoPublicable("no pasa")

    monkeypatch.setattr(newsroom, "escribir", _rechaza)
    topic = {"content_type": "clip", "title": "Arranca «Destrozares»",
             "summary": "Tramo 45-57s de «…» Motivos: …"}
    with pytest.raises(publisher.TextoRetenido):
        publisher._redactar_con_corpus(None, topic, extra="El concierto: Vigo")
    assert topic["texto_base"] == "Arranca «Destrozares»"


def test_el_summary_de_un_clip_no_llega_al_tema():
    it = InstagramQueueItem(title="Clip", content_type="clip",
                            summary="Tramo 45-57s de «…» Motivos: …")
    assert publisher._topic_from_item(None, it)["summary"] == ""


def test_si_no_se_puede_comprobar_el_clip_no_sale(db):
    """Falla cerrado: sin tabla `songs` (SQLite) el catálogo revienta, y eso es
    un «no», nunca un «sin comprobar, adelante»."""
    it = _item(db, content_type="clip", media_type="CLIP")
    db.add(VideoClip(video_id="x", url="https://youtu.be/x", start_s=0, end_s=10,
                     status="ready", queue_item_id=it.id, requested_by="auto"))
    db.commit()
    v = publisher.revisar_gate(db, it)
    assert not v.ok
    assert "no se pudo comprobar" in v.motivo


def test_una_noticia_que_no_pasa_las_guardas_al_repreparar_se_retiene(db, monkeypatch):
    """Si `publish` tiene que re-preparar y el redactor no pasa las guardas, no es
    un `failed`: eso gastaría intento y alimentaría el cortacircuitos."""
    from app.services.instagram import newsroom

    def _rechaza(db, item):
        raise newsroom.TextoNoPublicable("no pasa las guardas")

    monkeypatch.setattr(publisher, "prepare", _rechaza)
    it = _item(db, content_type="news", image_url=None, status="pending")
    publisher.publish(db, it)
    db.refresh(it)
    assert it.needs_human is True
    assert it.status == "pending"
    assert it.attempts == 0


@pytest.mark.parametrize("texto", [
    "«Material defectuoso» salió en 2011.",
    "Este material inédito nos recuerda la energía de la banda.",
    "De las 132 canciones, hay once de las que no consta que sonaran en directo.",
])
def test_material_como_palabra_normal_pasa(texto):
    """Ampliar las fórmulas de «falta de material» no puede tumbar un disco ni prosa."""
    assert gate_final.revisar(caption=texto).ok
