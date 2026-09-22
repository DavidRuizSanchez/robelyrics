"""La regla dura: lo que no se identifica, no se nombra.

Del item 348 (17-09-2026): el post afirmaba que «figuras del mundo del fútbol
como Guardiola reconocen la influencia de Robe». Ninguna fuente decía eso, y la
«Guardiola» de la noticia era la presidenta de la Junta de Extremadura.

La regla toma dos formas según el papel de la entidad, y la comprobación de que
se cumple es DETERMINISTA y posterior: se busca el nombre en el texto ya escrito.
No se le pide al modelo que obedezca y se da por hecho — pedírselo es lo que no
funcionó. Esta comprobación no gasta red ni clave de API, y corre en el CI.
"""
from __future__ import annotations

import pytest

from app.services import news_entities as ne
from app.services.instagram import newsroom


def _ent(surface, status, *, role="mentioned", label=None, kind="person"):
    return ne.ResolvedEntity(
        mention=ne.Mention(surface, kind, "ctx" if role == "subject" else "", role),
        status=status,
        label=label or surface,
        reason="motivo de prueba",
    )


IDENTIFICADA = _ent("María Guardiola", ne.WIKIDATA, role="subject")
DUDOSA = _ent("Guardiola", ne.AMBIGUOUS, role="mentioned")
PERDIDA = _ent("Fulano", ne.UNRESOLVED, role="mentioned")


# --- Buscar un nombre en un texto ------------------------------------------- #
def test_un_nombre_se_reconoce_con_tildes_o_sin_ellas():
    assert newsroom._aparece("María Guardiola", "habló Maria Guardiola ayer")


def test_un_nombre_no_casa_dentro_de_otra_palabra():
    """Sin fronteras de palabra, «Robe» casaría en «Robert» y silenciaríamos
    media Wikipedia."""
    assert newsroom._aparece("Robe", "Robe cantaba") is True
    assert newsroom._aparece("Robe", "Robert Smith cantaba") is False


def test_las_palabras_muy_cortas_no_disparan_solas():
    """«El» o «de» dentro de un nombre no pueden hacer que casen cosas al azar."""
    assert newsroom._aparece("de", "cualquier cosa de aquí") is False


# --- La regla del sujeto ----------------------------------------------------- #
def test_si_no_sabemos_de_quien_va_la_noticia_no_hay_post(monkeypatch):
    monkeypatch.setattr(ne, "resolve_all", lambda db, m, t: [
        _ent("Guardiola", ne.AMBIGUOUS, role="subject"),
    ])
    with pytest.raises(newsroom.SujetoNoIdentificado) as exc:
        newsroom.resolver_entidades(None, {"material": "x", "title": "t"})
    assert "Guardiola" in str(exc.value)


def test_una_mencion_secundaria_sin_identificar_no_tumba_el_post(monkeypatch):
    monkeypatch.setattr(ne, "resolve_all", lambda db, m, t: [IDENTIFICADA, PERDIDA])
    ents = newsroom.resolver_entidades(None, {"material": "x", "title": "t"})
    assert ne.silenciadas(ents) == ["Fulano"]


def test_basta_con_que_UN_sujeto_este_identificado(monkeypatch):
    """Una noticia puede tener varios protagonistas (la persona, el acto, el
    lugar). Perder uno secundario no la deja sin tema."""
    monkeypatch.setattr(ne, "resolve_all", lambda db, m, t: [
        IDENTIFICADA,
        _ent("No sé quién", ne.UNRESOLVED, role="subject"),
    ])
    ents = newsroom.resolver_entidades(None, {"material": "x", "title": "t"})
    assert "No sé quién" in ne.silenciadas(ents)


# --- La comprobación determinista -------------------------------------------- #
def test_se_caza_a_la_silenciada_que_se_cuela_en_el_texto():
    texto = "Es un honor que figuras del mundo del fútbol como Guardiola reconozcan…"
    assert newsroom.comprobar_silenciadas(texto, [IDENTIFICADA, DUDOSA]) == ["Guardiola"]


def test_la_identificada_si_puede_nombrarse():
    texto = "María Guardiola reivindicó el talento extremeño."
    assert newsroom.comprobar_silenciadas(texto, [IDENTIFICADA]) == []


def _escritor(monkeypatch, textos):
    """Hace que `editorial.enrich` escriba lo que le digamos, por turnos.

    `escribir` pasa el texto por TODAS las guardas de `caption_guard`; aquí solo
    se quiere ejercer la de lo silenciado, así que el resto se deja pasar. Ojo:
    no se sustituye `revisar` entero por un «todo bien» —eso haría verde el test
    hiciera lo que hiciese la guarda—, sino que se deja correr con las demás
    comprobaciones desactivadas por no tener material ni versos.
    """
    from app.services.instagram import caption_guard, editorial

    turnos = iter(textos)

    def _fake(topic):
        topic["caption_body"] = next(turnos)
        topic["headline"] = "titular"

    monkeypatch.setattr(editorial, "enrich", _fake)
    monkeypatch.setattr(caption_guard, "verificar_relaciones", lambda *a, **k: ([], []))
    monkeypatch.setattr(
        "app.services.lyric_guard.check_lyrics",
        lambda db, texto: type("R", (), {"blocking": [], "to_review": []})(),
    )


def test_si_el_texto_nombra_a_una_silenciada_se_reescribe(monkeypatch):
    _escritor(monkeypatch, [
        "Guardiola es un gran fan de Extremoduro.",   # se cuela
        "La presidenta reivindicó el talento.",       # limpio
    ])
    topic = {}
    avisos = newsroom.escribir(None, topic, [IDENTIFICADA, DUDOSA])
    assert "reescribió" in avisos[0]
    assert "Guardiola es un gran fan" not in topic["caption_body"]


def test_si_reincide_el_post_no_sale(monkeypatch):
    """Insistir sería confiar en que el modelo obedezca, que es justo lo que no
    funcionó. A la segunda, fuera."""
    _escritor(monkeypatch, ["Guardiola, futbolista.", "Otra vez Guardiola."])
    with pytest.raises(newsroom.TextoNoPublicable) as exc:
        newsroom.escribir(None, {}, [IDENTIFICADA, DUDOSA])
    assert "Guardiola" in str(exc.value)


def test_un_texto_limpio_a_la_primera_no_gasta_un_segundo_intento(monkeypatch):
    """Si se reescribiera siempre, se pagaría el doble por cada post."""
    llamadas = {"n": 0}
    _escritor(monkeypatch, ["La presidenta reivindicó el talento."] * 3)
    from app.services.instagram import editorial

    original = editorial.enrich

    def _contando(topic):
        llamadas["n"] += 1
        original(topic)

    monkeypatch.setattr(editorial, "enrich", _contando)
    assert newsroom.escribir(None, {}, [IDENTIFICADA, DUDOSA]) == []
    assert llamadas["n"] == 1


def test_la_comprobacion_corre_sin_clave_de_api(monkeypatch):
    """Es la guarda que habría parado el incidente, así que no puede depender de
    que haya red ni presupuesto: es una búsqueda de texto."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    texto = "Guardiola, entrenador, admira a Robe."
    assert newsroom.comprobar_silenciadas(texto, [DUDOSA]) == ["Guardiola"]


# --- Lo que ve el modelo ------------------------------------------------------ #
def test_el_prompt_lista_a_los_identificados_y_a_los_prohibidos():
    from app.services.instagram.editorial import _bloque_entidades

    bloque = _bloque_entidades([IDENTIFICADA, DUDOSA])
    assert "QUIÉN ES QUIÉN" in bloque
    assert "María Guardiola" in bloque
    assert "NO NOMBRAR" in bloque
    i_prohibidos = bloque.index("NO NOMBRAR")
    assert bloque.index("Guardiola", i_prohibidos) > i_prohibidos


def test_sin_entidades_el_prompt_no_se_ensucia():
    from app.services.instagram.editorial import _bloque_entidades

    assert _bloque_entidades([]) == ""
