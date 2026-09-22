"""Lo que se afirma en un caption tiene que estar en el artículo.

Del item 348, y costó encontrar qué era exactamente lo falso. El caption decía:

    «Es un honor que figuras del MUNDO DEL FÚTBOL como Guardiola reconozcan la
     influencia de Robe y su legado en el arte y la cultura extremeña.»

La relación —«Guardiola reconoce la influencia de Robe»— resulta que SÍ se
sostiene: el artículo habla de un lema del Día de Extremadura inspirado en él.
Lo falso era el inciso: llamarla «del mundo del fútbol», que contradice a la
entidad identificada, «política española». No es una relación entre entidades:
es un atributo.

Dos cosas más que se midieron por el camino y están en los docstrings del módulo:

  · `web_verify.verify_connection` daba por BUENA la afirmación inventada, y su
    evidencia era la propia noticia: confirma coaparición, no la relación.
  · `classify_fact('María Guardiola es fan de Extremoduro')` volvía `supported`
    con la evidencia «fan absoluto que soy de Extremoduro» — una frase de otra
    persona, pescada de una página cualquiera. La web no vale para esto.

Sin red salvo donde se dice: el LLM y el verificador se inyectan.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services import news_entities as ne
from app.services.instagram import caption_guard

FIXTURES = Path(__file__).parent / "fixtures" / "caso_guardiola"
ARTICULO = (FIXTURES / "noticia.txt").read_text()

PRESIDENTA = ne.ResolvedEntity(
    mention=ne.Mention("Guardiola", "person", "la presidenta de la Junta", "subject"),
    status=ne.WIKIDATA, label="María Guardiola", description="política española",
    qid="Q115151208",
)
CAPTION_PUBLICADO = (
    "Es un honor que figuras del mundo del fútbol como Guardiola reconozcan la "
    "influencia de Robe y su legado en el arte y la cultura extremeña."
)


@pytest.fixture()
def sin_llm(monkeypatch):
    """Ningún test de este fichero necesita el modelo. Si alguno lo llama sin
    decirlo, revienta en vez de pasar por un camino que no creía estar probando."""
    monkeypatch.setattr(
        "app.services.news_research._json",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no tocaba llamar al LLM")),
    )


# --- La guarda que cazaba el caso -------------------------------------------- #
def test_no_se_le_cambia_el_oficio_a_nadie():
    problemas = caption_guard.contradice_la_identidad(CAPTION_PUBLICADO, [PRESIDENTA])
    assert problemas
    assert "deporte" in problemas[0]
    assert "política española" in problemas[0]


def test_un_texto_fiel_no_se_bloquea():
    fiel = (
        "En el Día de Extremadura, la presidenta de la Junta reivindicó el talento "
        "de la región, con un lema que hace un guiño a Robe."
    )
    assert caption_guard.contradice_la_identidad(fiel, [PRESIDENTA]) == []


def test_se_mira_frase_a_frase_no_el_texto_entero():
    """Un post sobre música puede nombrar un estadio sin que eso convierta a
    nadie en futbolista. Si se mirase el texto completo, saltaría."""
    musico = ne.ResolvedEntity(
        mention=ne.Mention("Robe", "person", "", "subject"),
        status=ne.WIKIDATA, label="Roberto Iniesta", description="músico español",
    )
    texto = (
        "Roberto Iniesta llenó el Vicente Calderón. "
        "El estadio se quedó pequeño para el fútbol aquel año."
    )
    assert caption_guard.contradice_la_identidad(texto, [musico]) == []


def test_una_entidad_sin_descripcion_no_dispara_nada():
    de_casa = ne.ResolvedEntity(
        mention=ne.Mention("Extremoduro", "band", "", "subject"),
        status=ne.CORPUS, label="Extremoduro",
    )
    assert caption_guard.contradice_la_identidad(CAPTION_PUBLICADO, [de_casa]) == []


# --- Las relaciones se comprueban contra el ARTÍCULO -------------------------- #
def test_la_relacion_que_esta_en_el_articulo_pasa_sin_preguntar_a_nadie(sin_llm):
    """Atajo determinista: si está escrito, no se gasta una llamada."""
    rel = {"a": "Guardiola", "relacion": "reivindica el talento", "b": "Extremadura"}
    assert caption_guard._en_el_material(rel, ARTICULO) is True


def test_una_relacion_que_no_esta_no_se_da_por_buena(sin_llm):
    rel = {"a": "Guardiola", "relacion": "es fan de", "b": "Extremoduro"}
    assert caption_guard._en_el_material(rel, ARTICULO) is False


def test_la_cita_del_juez_tiene_que_estar_en_el_articulo(monkeypatch):
    """El juez propone y el artículo dispone: si devuelve una cita que no está,
    se la ha inventado y no vale. Es el mismo patrón que la extracción de
    entidades y que `validated_event_date`."""
    monkeypatch.setattr(
        "app.services.news_research._json",
        lambda *a, **k: {"respalda": True, "cita": "esta frase no está en el artículo"},
    )
    r = caption_guard._lo_dice_el_articulo("X es fan de Y", ARTICULO)
    assert r["verdict"] == "not_found"


def test_con_una_cita_de_verdad_si_pasa(monkeypatch):
    cita = "La presidenta de la Junta de Extremadura"
    assert cita in ARTICULO
    monkeypatch.setattr(
        "app.services.news_research._json",
        lambda *a, **k: {"respalda": True, "cita": cita},
    )
    r = caption_guard._lo_dice_el_articulo("Guardiola preside la Junta", ARTICULO)
    assert r["verdict"] == "supported"
    assert r["source"] == "material"


def test_sin_articulo_no_se_respalda_nada(sin_llm):
    r = caption_guard._lo_dice_el_articulo("lo que sea", "")
    assert r["verdict"] == "not_found"


def test_la_web_no_decide_sobre_las_relaciones(monkeypatch):
    """Medido: `verify_connection('Guardiola','Robe')` devolvía confirmado, y su
    evidencia era la propia noticia. Si alguien la recablea aquí, este test cae."""
    def _explota(*a, **k):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("la web no decide si una relación es cierta")

    monkeypatch.setattr("app.services.web_verify.verify_connection", _explota)
    monkeypatch.setattr("app.services.web_verify.classify_fact", _explota)
    monkeypatch.setattr(
        "app.services.news_research._json",
        lambda *a, **k: {"respalda": False, "cita": ""},
    )
    bloqueos, claims = caption_guard.verificar_relaciones(
        "Guardiola es fan de Extremoduro.", ARTICULO, [PRESIDENTA]
    )
    assert bloqueos or claims == []


def test_las_dos_formas_del_nombre_van_a_la_lista():
    """El texto nombra a alguien entero una vez y por el apellido el resto. Con
    solo el nombre canónico en la lista, el extractor no veía la relación en una
    frase que decía «Guardiola», y la afirmación inventada pasaba entera."""
    conocidas = caption_guard._entidades_conocidas([PRESIDENTA])
    assert "María Guardiola" in conocidas
    assert "Guardiola" in conocidas
    assert "Robe" in conocidas and "Extremoduro" in conocidas


# --- El veredicto en conjunto -------------------------------------------------- #
def test_el_caption_publicado_hoy_no_saldria(sin_llm):
    """Sin LLM: la guarda que lo para es determinista, y eso importa — corre en
    el CI, sin clave y sin gastar un céntimo."""
    v = caption_guard.Veredicto()
    v.bloqueos.extend(caption_guard.contradice_la_identidad(CAPTION_PUBLICADO, [PRESIDENTA]))
    assert v.ok is False


def test_un_veredicto_con_avisos_pero_sin_bloqueos_si_publica():
    v = caption_guard.Veredicto(avisos=["mira esto"])
    assert v.ok is True


def test_una_palabra_no_casa_dentro_de_otra(sin_llm):
    """«fan» casaba dentro de «infantil» y daba por respaldada la afirmación
    «Guardiola es fan de Extremoduro» contra un artículo que ni la menciona.
    Mismo bug que «carrera» dentro de «su carrera» en el filtro de YouTube."""
    material = "El programa infantil de Extremadura habló de Guardiola y Extremoduro."
    rel = {"a": "Guardiola", "relacion": "es fan de", "b": "Extremoduro"}
    assert caption_guard._en_el_material(rel, material) is False


def test_el_articulo_y_el_caption_no_la_llaman_igual(sin_llm):
    """El agujero que destapó el barrido de `audit_identidad` sobre el caso real.

    El artículo dice «María Guardiola», así que la mención consolidada tiene ese
    nombre. Pero el caption decía solo «Guardiola». Buscando únicamente el nombre
    completo, la guarda no encontraba la frase y el post pasaba: el script decía
    «nada que revisar» justo del post que había que cazar. El test anterior no lo
    veía porque usaba ya el nombre corto como `surface`.
    """
    como_viene_del_articulo = ne.ResolvedEntity(
        mention=ne.Mention("María Guardiola", "person", "la presidenta", "subject"),
        status=ne.WIKIDATA, label="María Guardiola", description="política española",
    )
    problemas = caption_guard.contradice_la_identidad(
        CAPTION_PUBLICADO, [como_viene_del_articulo]
    )
    assert problemas, "el caption dice «Guardiola» y la entidad es «María Guardiola»"
    assert "deporte" in problemas[0]


def test_un_nombre_de_una_sola_palabra_no_genera_variantes_raras(sin_llm):
    assert caption_guard._variantes("Extremoduro") == ["Extremoduro"]
    assert "Guardiola" in caption_guard._variantes("María Guardiola")


def test_tambien_se_protege_a_quien_no_esta_en_ninguna_base_de_datos(sin_llm):
    """La calibración del 23-09-2026 permite nombrar a quien el artículo
    describe, aunque no exista en Wikidata. Pero seguir permitiéndolo NO puede
    significar que se le pueda cambiar el oficio: la referencia pasa a ser lo que
    dice el artículo."""
    concursante = ne.ResolvedEntity(
        mention=ne.Mention("Moisés", "person", "concursante riojano", "subject"),
        status=ne.AMBIGUOUS, label=None, description=None,
    )
    assert concursante.silenciada is False
    texto = "Moisés, el diputado del Parlamento, cantó So payaso."
    problemas = caption_guard.contradice_la_identidad(texto, [concursante])
    assert problemas, "le ha cambiado el oficio y nadie lo ha parado"
    assert "concursante riojano" in problemas[0]


# --------------------------------------------------------------------------- #
# Lo que el sitio ya sabe no se le pide al artículo
# --------------------------------------------------------------------------- #
def test_una_relacion_entre_dos_entidades_de_casa_no_pasa_por_el_verificador(monkeypatch):
    """Medido: una noticia legítima (el Sinfónico Extremo de Béjar) se caía dos
    veces porque el extractor sacaba «Robe — versionó a — Extremoduro» y el
    artículo, claro, no lo decía. El paso 6 existe para no AFIRMAR algo nuevo
    sobre terceros, no para volver a demostrar de qué va esta web."""
    llamadas = []
    monkeypatch.setattr(
        caption_guard, "_json",
        lambda *a, **k: {"relaciones": [
            {"a": "Robe", "relacion": "versionó a", "b": "Extremoduro"},
        ]},
        raising=False,
    )
    monkeypatch.setattr(
        caption_guard, "_lo_dice_el_articulo",
        lambda *a, **k: llamadas.append(a) or {"verdict": "not_found", "evidence": ""},
    )
    import app.services.news_research as nr
    monkeypatch.setattr(
        nr, "_json",
        lambda *a, **k: {"relaciones": [
            {"a": "Robe", "relacion": "versionó a", "b": "Extremoduro"},
        ]},
    )

    bloqueos, claims = caption_guard.verificar_relaciones(
        "Un homenaje sinfónico a Robe y Extremoduro en Béjar.",
        "La banda tocará canciones del grupo.",
        [],
    )
    assert bloqueos == []
    assert llamadas == [], "no se gasta una llamada en lo que ya sabemos"
    assert claims[0]["source"] == "corpus"


def test_una_relacion_con_un_tercero_sigue_yendo_al_verificador(monkeypatch):
    """El agujero que NO se abre: María Guardiola no es entidad de casa."""
    import app.services.news_research as nr
    monkeypatch.setattr(
        nr, "_json",
        lambda *a, **k: {"relaciones": [
            {"a": "María Guardiola", "relacion": "es fan de", "b": "Extremoduro"},
        ]},
    )
    monkeypatch.setattr(
        caption_guard, "_lo_dice_el_articulo",
        lambda *a, **k: {"verdict": "not_found", "evidence": ""},
    )
    bloqueos, _ = caption_guard.verificar_relaciones(
        "María Guardiola es fan de Extremoduro.", "El artículo no dice eso.",
        [PRESIDENTA],
    )
    assert bloqueos, "una afirmación nueva sobre un tercero sigue bloqueando"
