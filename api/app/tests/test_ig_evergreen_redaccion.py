"""El evergreen también lo escribe alguien, pero solo con material delante.

La regla vieja era «en evergreen no se llama al LLM», y tenía razón en lo que
protegía: el texto sale del corpus verificado y un carrusel inventado sería el
fallo que todo el proyecto evita. Lo que se cambia es el matiz: la regla no era
«no usar IA», era «no inventar». Con material de casa delante y los mismos gates
que una noticia, se escribe; sin material, el post sale exactamente como salía.
"""
from __future__ import annotations

from app.services.instagram import captions, publisher
from app.services.instagram.material import Material


def _topic_verso(**kw) -> dict:
    base = {
        "title": "Dejo las ventanas sin cerrar",
        "caption_body": "Dejo las ventanas sin cerrar",
        "content_type": "quote",
        "content_key": "quote:line_1",
        "corpus": {"song": "Interludio", "album": "La Ley Innata", "year": 2008,
                   "artist": "Extremoduro"},
        "summary": "«Interludio» · Extremoduro · La Ley Innata (2008)",
        "verse": {},
        "tone": "neutral",
    }
    base.update(kw)
    return base


def test_sin_material_no_se_llama_al_modelo(monkeypatch):
    """Lo que protegía la regla vieja, intacto."""
    llamadas = []
    monkeypatch.setattr(publisher.material_ig, "reunir", lambda *a, **k: Material())
    monkeypatch.setattr(
        publisher.newsroom, "escribir",
        lambda *a, **k: llamadas.append(a) or [],
    )
    topic = _topic_verso()
    publisher._redactar_con_corpus(None, topic)

    assert llamadas == []
    assert topic["caption_body"] == "Dejo las ventanas sin cerrar"
    assert "slides" not in topic


def test_con_material_se_escribe_y_el_verso_entra_en_el_anclaje(monkeypatch):
    """El verso es un hecho del post tanto como lo que dice el corpus: si no
    entrara en el material, `anclaje_factual` tumbaría el texto que habla de él."""
    visto = {}
    monkeypatch.setattr(
        publisher.material_ig, "reunir",
        lambda *a, **k: Material(prompt="LO QUE DIJO ROBE · la escribí en una noche"),
    )

    def _fake_escribir(db, topic, entidades, *, material=None, verificar_rel=True,
                       material_verificable=None):
        visto["material"] = material
        visto["verificar_rel"] = verificar_rel
        visto["entidades"] = entidades
        return ["un aviso"]

    monkeypatch.setattr(publisher.newsroom, "escribir", _fake_escribir)
    topic = _topic_verso()
    publisher._redactar_con_corpus(None, topic)

    assert "Dejo las ventanas sin cerrar" in visto["material"]
    assert "LO QUE DIJO ROBE" in visto["material"]
    # Sobre el corpus propio no hay relación ajena que verificar, y el paso caro
    # sí puede inventarse un bloqueo.
    assert visto["verificar_rel"] is False
    assert visto["entidades"] == []
    assert topic["avisos"] == ["un aviso"]


def test_si_las_guardas_tumban_el_texto_el_post_sale_igual(monkeypatch):
    """Un evergreen no se pierde por esto: su texto ya era publicable antes de
    que existiera el redactor."""
    monkeypatch.setattr(
        publisher.material_ig, "reunir", lambda *a, **k: Material(prompt="material")
    )

    def _revienta(*a, **k):
        raise publisher.newsroom.TextoNoPublicable("se inventó un verso")

    monkeypatch.setattr(publisher.newsroom, "escribir", _revienta)
    topic = _topic_verso(slides=[{"kicker": "X", "text": "y"}], cierre="z")
    publisher._redactar_con_corpus(None, topic)

    assert topic["caption_body"] == "Dejo las ventanas sin cerrar"
    assert "slides" not in topic
    assert "cierre" not in topic
    assert any("texto de siempre" in a for a in topic["avisos"])


# --------------------------------------------------------------------------- #
# La regla del nombre, sobre el caption ENTERO
# --------------------------------------------------------------------------- #
def test_la_regla_del_nombre_corre_sobre_todo_el_caption():
    """Antes solo corría dentro de `editorial`, así que un «Robe Iniesta»
    escrito en un molde, en el CTA o en un hashtag llegaba publicado."""
    topic = _topic_verso(
        content_type="news",
        content_key="news:1",
        caption_body="Un homenaje a Robe Iniesta en Plasencia.",
        corpus={},
        summary="",
    )
    caption = captions.build(None, topic)
    assert "Robe Iniesta" not in caption


def test_el_comentario_del_verso_acompana_a_la_atribucion():
    """En los posts de verso la imagen se basta, pero lo que se ha escrito SOBRE
    el verso sí aporta: va detrás del dato que la gente pregunta."""
    topic = _topic_verso(caption_body="La grabaron en Madrid en 2008, y se nota.")
    caption = captions.build(None, topic)
    assert "La grabaron en Madrid en 2008" in caption
    assert caption.index("Interludio") < caption.index("La grabaron")
