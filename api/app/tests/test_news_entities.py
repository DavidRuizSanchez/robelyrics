"""Quién es quién: el caso Guardiola, con los payloads reales de las APIs.

Item 348, publicado el 17-09-2026. Una noticia sobre el Día de Extremadura cuyo
titular decía solo «Guardiola» salió con fotos de Pep Guardiola y afirmando que
«figuras del mundo del fútbol como Guardiola reconocen la influencia de Robe».
El artículo decía en su segunda frase: «La presidenta de la Junta de Extremadura,
María Guardiola».

Los payloads de `fixtures/caso_guardiola/` son literales, grabados de Wikidata y
Wikipedia el 22-09-2026. En los tests de desambiguación el orden de candidatos se
INVIERTE a propósito: si el acierto dependiera de que Wikidata devuelva primero
al bueno, el test no probaría nada — y precisamente lo que rompió en producción
fue quedarse con el primero.

Sin red: Wikidata y Wikipedia se inyectan.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import news_entities as ne

FIXTURES = Path(__file__).parent / "fixtures" / "caso_guardiola"
EXTRACTOS: dict[str, str] = json.loads(
    (FIXTURES / "wikipedia_extractos.json").read_text()
)


def _cands(fichero: str) -> list[dict]:
    return json.loads((FIXTURES / fichero).read_text())["search"]


CANDS_NOMBRE_COMPLETO = _cands("wikidata_search_cuerpo.json")   # María Guardiola
CANDS_APELLIDO_SOLO = _cands("wikidata_search_titular.json")    # Guardiola a secas
CANDS_HOMONIMO = _cands("wikidata_search_homonimo.json")        # Pep Guardiola

CONTEXTO_REAL = "La presidenta de la Junta de Extremadura, María Guardiola, ha felicitado"
QID_PRESIDENTA = "Q115151208"
QID_ENTRENADOR = "Q164038"


@pytest.fixture()
def wiki(monkeypatch):
    """Fija lo que devuelven Wikidata y Wikipedia. Devuelve el registro de usos."""
    def _montar(candidatos: list[dict], *, extractos: dict | None = None):
        pedidos: list[str] = []

        def _busca(surface, **kw):  # noqa: ANN001, ANN003
            pedidos.append(surface)
            return candidatos

        monkeypatch.setattr(ne, "_candidatos_wikidata", _busca)
        tabla = EXTRACTOS if extractos is None else extractos
        monkeypatch.setattr(
            "app.services.web_verify.wikipedia_extract",
            lambda titulo, lang="es": tabla.get(titulo, ""),
        )
        # El juez solo debe entrar cuando el contexto no decide. Si un test no lo
        # espera, que reviente en vez de tapar el fallo con una llamada de red.
        monkeypatch.setattr(
            ne, "_juez",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("el juez no debía entrar")),
        )
        return pedidos

    return _montar


@pytest.fixture()
def sin_corpus(monkeypatch):
    """Nadie de estos está en el corpus del proyecto."""
    monkeypatch.setattr(ne, "_buscar_en_corpus", lambda db, m: None)


# --- El caso ---------------------------------------------------------------- #
def test_el_contexto_de_la_noticia_elige_a_la_presidenta(wiki, sin_corpus):
    """Invertido el orden: la presidenta va la ÚLTIMA. Aun así tiene que ganar,
    porque su ficha dice «presidenta de la Junta de Extremadura» y el contexto
    del artículo también."""
    wiki(list(reversed(CANDS_NOMBRE_COMPLETO)))
    r = ne.resolve(None, ne.Mention("María Guardiola", "person", CONTEXTO_REAL, "subject"))
    assert r.status == ne.WIKIDATA
    assert r.qid == QID_PRESIDENTA
    assert r.description == "política española"


def test_jamas_el_entrenador(wiki, sin_corpus):
    """Con el entrenador metido en la baraja y de primero."""
    wiki(CANDS_HOMONIMO[:1] + CANDS_NOMBRE_COMPLETO)
    r = ne.resolve(None, ne.Mention("María Guardiola", "person", CONTEXTO_REAL, "subject"))
    assert r.qid != QID_ENTRENADOR
    assert r.qid == QID_PRESIDENTA


def test_sin_contexto_no_hay_entidad(wiki, sin_corpus):
    """Lo que el titular daba: «Guardiola», sin decir quién es. Wikidata devuelve
    un apellido, un género de plantas y tres pueblos — y ninguna de las dos
    personas. Elegir el primero es exactamente lo que se hacía."""
    wiki(CANDS_APELLIDO_SOLO)
    r = ne.resolve(None, ne.Mention("Guardiola", "person", "", "subject"))
    assert r.status == ne.AMBIGUOUS
    assert r.silenciada is True
    assert r.nombre_publicable is None
    assert "no dice quién es" in r.reason


def test_dos_politicas_no_las_separa_el_oficio(wiki, sin_corpus):
    """El segundo candidato del nombre completo es «política portuguesa». Un
    léxico de oficios las daría por igual de buenas: lo que separa es el sitio,
    y eso solo está en el contexto de la noticia."""
    descripciones = [c.get("description") for c in CANDS_NOMBRE_COMPLETO]
    assert "política española" in descripciones
    assert "política portuguesa" in descripciones

    wiki(CANDS_NOMBRE_COMPLETO)
    r = ne.resolve(None, ne.Mention("María Guardiola", "person", CONTEXTO_REAL, "subject"))
    assert r.qid == QID_PRESIDENTA


def test_un_contexto_de_futbol_si_lleva_al_entrenador(wiki, sin_corpus):
    """La guarda no es «nunca un deportista»: es «lo que diga el artículo». Si la
    noticia va del entrenador, resolver a otro sería el mismo error al revés."""
    wiki(CANDS_HOMONIMO, extractos=EXTRACTOS)
    r = ne.resolve(
        None,
        ne.Mention("Pep Guardiola", "person", "el exfutbolista y entrenador español", "mentioned"),
    )
    assert r.qid == QID_ENTRENADOR


def test_si_wikidata_no_conoce_a_nadie_no_se_inventa(wiki, sin_corpus):
    wiki([])
    r = ne.resolve(None, ne.Mention("Zerkalov Pipistrelli", "person", "un cantante", "mentioned"))
    assert r.status == ne.UNRESOLVED
    assert r.silenciada is True


# --- La extracción: el LLM propone, el artículo dispone --------------------- #
def _extraer(monkeypatch, material, crudas):
    monkeypatch.setattr(
        "app.services.news_research._json", lambda *a, **k: {"entities": crudas}
    )
    return ne.extract_mentions(material, "titular")


def test_una_entidad_que_no_esta_en_el_articulo_se_cae(monkeypatch):
    """La red que separa un extractor de entidades de un inventor de entidades."""
    ms = _extraer(monkeypatch, "El acto se celebró en Plasencia.", [
        {"surface": "Plasencia", "kind": "place", "context": "", "role": "subject"},
        {"surface": "Pep Guardiola", "kind": "person", "context": "el entrenador", "role": "mentioned"},
    ])
    assert [m.surface for m in ms] == ["Plasencia"]


def test_un_contexto_inventado_se_tira_pero_la_entidad_se_queda(monkeypatch):
    """Tirar la mención entera sería excesivo; tirar el contexto inventado es lo
    justo. Y sin contexto la entidad acaba silenciada, que es lo correcto: es
    justo un contexto falso lo que llevaría a elegir al homónimo."""
    ms = _extraer(monkeypatch, "Robe Iniesta fundó Extremoduro.", [
        {"surface": "Robe Iniesta", "kind": "person",
         "context": "el famoso entrenador de fútbol", "role": "subject"},
    ])
    assert len(ms) == 1
    assert ms[0].context == ""


def test_el_apellido_suelto_se_funde_en_el_nombre_completo(monkeypatch):
    """El artículo nombra a alguien entero una vez y por el apellido el resto.
    Sin fundirlos, «Guardiola» no resolvería y la regla dura silenciaría a una
    persona que el propio artículo identifica."""
    material = "La presidenta María Guardiola habló. Guardiola apeló a la unidad."
    ms = _extraer(monkeypatch, material, [
        {"surface": "Guardiola", "kind": "person", "context": "", "role": "mentioned"},
        {"surface": "María Guardiola", "kind": "person",
         "context": "La presidenta", "role": "subject"},
    ])
    assert [m.surface for m in ms] == ["María Guardiola"]
    assert ms[0].role == "subject", "el papel más fuerte de los dos manda"
    assert ms[0].context == "La presidenta"


def test_no_se_funden_cosas_de_distinta_naturaleza(monkeypatch):
    """«Extremadura» (lugar) y «Canal Extremadura» (medio) son dos cosas."""
    material = "Extremadura celebra su día. Lo contó Canal Extremadura."
    ms = _extraer(monkeypatch, material, [
        {"surface": "Extremadura", "kind": "place", "context": "", "role": "subject"},
        {"surface": "Canal Extremadura", "kind": "org", "context": "", "role": "mentioned"},
    ])
    assert {m.surface for m in ms} == {"Extremadura", "Canal Extremadura"}


def test_sin_articulo_no_se_extrae_nada(monkeypatch):
    def _explota(*a, **k):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("no se llama al modelo sin material")

    monkeypatch.setattr("app.services.news_research._json", _explota)
    assert ne.extract_mentions("", "titular") == []


def test_da_igual_como_bautice_el_modelo_la_lista(monkeypatch):
    """La primera versión devolvió CERO menciones sobre un artículo del que sacaba
    todo, solo porque el modelo llamó a la lista `entities` y el código buscaba
    `menciones`. Un fallo así no revienta: devuelve vacío y parece que no hay
    nadie en la noticia."""
    material = "Extremoduro tocó en Plasencia."
    fila = [{"surface": "Plasencia", "kind": "place", "context": "", "role": "subject"}]
    for clave in ("entities", "menciones", "entidades", "lo_que_sea"):
        monkeypatch.setattr(
            "app.services.news_research._json",
            lambda *a, _c=clave, **k: {_c: fila},  # atado: si no, ruff avisa (B023)
        )
        assert [m.surface for m in ne.extract_mentions(material, "t")] == ["Plasencia"]


# --- Utilidades de la regla dura -------------------------------------------- #
def test_las_silenciadas_son_las_que_no_resuelven():
    ok = ne.ResolvedEntity(ne.Mention("Extremoduro", "band"), ne.CORPUS, label="Extremoduro")
    dudosa = ne.ResolvedEntity(ne.Mention("Guardiola", "person"), ne.AMBIGUOUS)
    perdida = ne.ResolvedEntity(ne.Mention("X", "person"), ne.UNRESOLVED)
    assert ne.silenciadas([ok, dudosa, perdida]) == ["Guardiola", "X"]
    assert ok.resuelta and not dudosa.resuelta and not perdida.resuelta


# --- Por qué la heurística vieja no podía funcionar ------------------------- #
def test_la_heuristica_vieja_no_distingue_a_un_entrenador_de_una_presidenta():
    """Documenta el bug en la suite, para que no vuelva por la puerta de atrás.

    `photo_finder._wikidata_photo` ordena los candidatos poniendo delante a quien
    tenga pistas de MÚSICA en la descripción (`_DOMINIO_HINTS`). Con «Guardiola»
    eso es un no-op: ni el entrenador ni la presidenta son músicos, así que el
    orden no se mueve y gana el primero que devuelva Wikidata — el más notorio.
    """
    from app.services.instagram.photo_finder import _DOMINIO_HINTS

    baraja = CANDS_HOMONIMO[:1] + CANDS_NOMBRE_COMPLETO[:1]  # entrenador, presidenta
    ordenada = sorted(baraja, key=lambda c: 0 if any(
        h in (c.get("description") or "").lower() for h in _DOMINIO_HINTS
    ) else 1)

    assert ordenada[0]["id"] == QID_ENTRENADOR, (
        "si esto cambia, el sort viejo ya distingue y este test sobra"
    )
    assert not any(
        h in (c.get("description") or "").lower()
        for c in baraja for h in _DOMINIO_HINTS
    ), "ninguno de los dos casa con el léxico musical: por eso no desempataba"
