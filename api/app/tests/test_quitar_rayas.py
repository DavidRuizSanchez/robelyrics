"""Fuera la raya larga de toda la web (David, 12-11-2026).

Medido en el crawl de las 388 URLs del sitemap: 193 rayas en 182 páginas. Casi
todas venían de plantillas (pie de la letra, tabla de persona, JSON-LD de vídeo)
y de títulos de YouTube guardados en la BD; una, de un cuerpo de post escrito
con incisos. Los casos de abajo son literales de esas páginas.
"""
from __future__ import annotations

from sqlalchemy import select

from app.db.models import Album, Artist, Person, SeoContent, Song
from app.services import page_monitor as pm
from app.services.text_sanitizer import quitar_rayas
from app.tests.test_person_visibility import db  # noqa: F401 — fixture SQLite


def test_inciso_del_cuerpo_real():
    antes = ("Aunque la causa de su muerte no se hizo pública —el comunicado de su agencia no "
             "dio detalles médicos, como recogió elDiario.es —, en noviembre de 2024 Robe")
    assert quitar_rayas(antes) == (
        "Aunque la causa de su muerte no se hizo pública, el comunicado de su agencia no "
        "dio detalles médicos, como recogió elDiario.es, en noviembre de 2024 Robe")


def test_inciso_cerrado_con_raya():
    assert quitar_rayas("Robe —que nació en Plasencia— grabó Agila.") == (
        "Robe, que nació en Plasencia, grabó Agila.")


def test_raya_entre_espacios_y_pegada():
    assert quitar_rayas("Agila — el disco") == "Agila, el disco"
    assert quitar_rayas("rock—urbano") == "rock, urbano"


def test_lista_y_dialogo():
    assert quitar_rayas("— uno\n— dos") == "- uno\n- dos"
    assert quitar_rayas("—Hola, Robe.") == "Hola, Robe."


def test_titulo_de_video():
    assert quitar_rayas("Leiva — Caída Libre (Video Oficial) ft. Robe", titulo=True) == (
        "Leiva - Caída Libre (Video Oficial) ft. Robe")


def test_no_toca_urls_ni_destinos_de_enlace():
    md = "Ver [el vídeo](https://ejemplo.com/a—b) y https://otra.com/x—y — luego."
    assert quitar_rayas(md) == "Ver [el vídeo](https://ejemplo.com/a—b) y https://otra.com/x—y, luego."


def test_deja_la_semirraya_de_los_rangos():
    assert quitar_rayas("Batería (1988–1992)") == "Batería (1988–1992)"


def test_sin_rayas_devuelve_lo_mismo():
    s = "Nada que quitar."
    assert quitar_rayas(s) is s
    assert quitar_rayas(None) is None


def test_el_listener_quita_rayas_al_guardar(db):  # noqa: F811
    p = Person(slug="x", full_name="Luis — von Fanta", bio_short="Batería —primero— de Extremoduro.")
    db.add(p)
    db.flush()
    db.add(SeoContent(entity_type="person", entity_id=p.id, slug="x", body_md="Uno — dos.",
                      meta_title="Luis von Fanta — batería", published=True,
                      entities=[{"name": "A — B"}], secondary_keywords=[], outline=[]))
    art = Artist(slug="robe", name="Robe")
    db.add(art)
    db.flush()
    alb = Album(slug="d", title="D", year=2015, artist_id=art.id)
    db.add(alb)
    db.flush()
    db.add(Song(slug="s", title="S", album_id=alb.id, youtube_title="Leiva — Caída Libre"))
    db.commit()
    s = db.execute(select(SeoContent)).scalar_one()
    assert s.body_md == "Uno, dos." and s.meta_title == "Luis von Fanta, batería"
    assert s.entities == [{"name": "A, B"}]
    persona = db.execute(select(Person)).scalar_one()
    assert persona.bio_short == "Batería, primero, de Extremoduro."
    assert persona.full_name == "Luis — von Fanta"  # los nombres no se tocan
    assert db.execute(select(Song)).scalar_one().youtube_title == "Leiva - Caída Libre"


def test_el_monitor_cuenta_las_rayas_y_avisa_si_suben():
    def foto(texto):
        html = (f'<html><head><title>T</title><meta name="description" content="{texto}"/>'
                f'</head><body><main><h1>H</h1><p>{texto}</p></main></body></html>')
        return {"status": 200, "final_url": "https://entreinteriores.com/x", "cadena": [],
                "ms": 100, "campos": pm.parse(html, path="/x")}
    limpia, sucia = foto("Sin rayas."), foto("Con — raya.")
    assert limpia["campos"]["rayas"] == 0 and sucia["campos"]["rayas"] == 2
    assert [c.campo for c in pm.diff(limpia, sucia, path="/x")].count("rayas") == 1
    assert "rayas" not in [c.campo for c in pm.diff(sucia, limpia, path="/x")]
