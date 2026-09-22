"""La foto: procedencia primero, y nunca una cara sin acreditar.

Del item 348: `photo_finder` pedía al modelo una frase de búsqueda sacada del
titular, se la daba a Google Images y elegía uno de los quince primeros con
`md5(título) % len(pool)`. Sin mirar el resultado — ni el campo `title`, que la
API sí devuelve. El titular decía «Guardiola», el prompt ordenaba «añade SIEMPRE
contexto», salió «Guardiola entrenador de fútbol» y el dado cayó en Pep.

Aquí la búsqueda se CONSTRUYE desde la entidad ya identificada, y ningún
candidato se publica sin que algo ajeno lo acredite.

Sin red: Commons, Wikidata, Google y la visión se inyectan.
"""
from __future__ import annotations

import pytest

from app.services import identity_guard, image_guard
from app.services import news_entities as ne
from app.services.instagram import identity_photo

PRESIDENTA = ne.ResolvedEntity(
    mention=ne.Mention("María Guardiola", "person", "la presidenta de la Junta", "subject"),
    status=ne.WIKIDATA, label="María Guardiola", description="política española",
    qid="Q115151208",
)
ENTRENADOR_DESC = "futbolista y entrenador español"
TOPIC = {"title": "Guardiola reivindica el talento"}


# --- El conflicto de dominio (mismo país, distinto oficio) ------------------ #
def test_una_foto_de_entrenador_no_acredita_a_una_politica(monkeypatch):
    """Lo que `_FOREIGN_HINTS` no puede ver: los dos son españoles."""
    monkeypatch.setattr(image_guard, "commons_evidence", lambda *a, **k: {
        "categories": ["Pep Guardiola", "Manchester City F.C. managers"],
        "description": "Pep Guardiola en el banquillo", "missing": False,
    })
    v = image_guard.verify_provenance(
        entity_name="Pep Guardiola",
        image_url="https://upload.wikimedia.org/wikipedia/commons/1/11/Guardiola.jpg",
        expected_terms="política española",
    )
    assert v.status == "homonym_risk"
    assert v.publishable is False
    assert v.needs_human is True


def test_sin_expected_terms_el_veredicto_es_el_de_siempre(monkeypatch):
    """`verify_provenance` mueve el cron de imágenes de las 04:40. Si el
    parámetro nuevo cambiara algo por omisión, abriría erratas sobre fotos buenas
    de la web pública."""
    monkeypatch.setattr(image_guard, "commons_evidence", lambda *a, **k: {
        "categories": ["Pep Guardiola", "Manchester City F.C. managers"],
        "description": "Pep Guardiola en el banquillo", "missing": False,
    })
    v = image_guard.verify_provenance(
        entity_name="Pep Guardiola",
        image_url="https://upload.wikimedia.org/wikipedia/commons/1/11/Guardiola.jpg",
    )
    assert v.status == "accredited"


def test_una_foto_del_oficio_esperado_pasa(monkeypatch):
    monkeypatch.setattr(image_guard, "commons_evidence", lambda *a, **k: {
        "categories": ["Presidentas de la Junta de Extremadura", "Partido Popular"],
        "description": "María Guardiola", "missing": False,
    })
    v = image_guard.verify_provenance(
        entity_name="María Guardiola",
        image_url="https://upload.wikimedia.org/wikipedia/commons/2/21/MG.jpg",
        expected_terms="política española",
    )
    assert v.status == "accredited"


def test_una_foto_de_musico_no_se_marca_por_mencionar_un_estadio(monkeypatch):
    """Exigir las dos condiciones —que case con otro Y que no case con el
    esperado— evita el falso positivo obvio: un músico tocando en un estadio."""
    monkeypatch.setattr(image_guard, "commons_evidence", lambda *a, **k: {
        "categories": ["Roberto Iniesta", "Rock musicians",
                       "Concerts at the Estadio Vicente Calderón"],
        "description": "Roberto Iniesta en concierto", "missing": False,
    })
    v = image_guard.verify_provenance(
        entity_name="Roberto Iniesta",
        image_url="https://upload.wikimedia.org/wikipedia/commons/3/33/Robe.jpg",
        expected_terms="músico español",
    )
    assert v.status == "accredited"


# --- El filtro determinista de los candidatos de Google -------------------- #
def _cand(title="", page_url="", site=""):
    return {"url": "https://x/1.jpg", "thumb": "", "title": title,
            "page_url": page_url, "site": site}


def test_un_resultado_que_no_nombra_a_la_entidad_se_cae():
    assert identity_photo._casa_el_candidato(
        _cand(title="Pep Guardiola gana la Champions", site="Marca"), PRESIDENTA
    ) is False


def test_hace_falta_el_nombre_Y_algo_que_lo_distinga():
    """«María Guardiola» sola no basta si nada dice que es la política: hay una
    homónima portuguesa, también política, y una investigadora."""
    assert identity_photo._casa_el_candidato(
        _cand(title="María Guardiola", site="Fotos"), PRESIDENTA
    ) is False
    assert identity_photo._casa_el_candidato(
        _cand(title="María Guardiola, política española", site="Wikipedia"), PRESIDENTA
    ) is True


def test_el_dominio_de_la_pagina_tambien_cuenta():
    assert identity_photo._casa_el_candidato(
        _cand(title="María Guardiola", page_url="https://es.wikipedia.org/wiki/María_Guardiola_política"),
        PRESIDENTA,
    ) is True


def test_un_resultado_sin_texto_ninguno_no_se_da_por_bueno():
    assert identity_photo._casa_el_candidato(_cand(), PRESIDENTA) is False


# --- La cascada ------------------------------------------------------------- #
@pytest.fixture()
def sin_fuentes(monkeypatch):
    """Todo apagado; cada test enciende lo suyo. Lo que no se encienda y se use,
    revienta: así un test no pasa por un camino que no creía estar probando."""
    monkeypatch.setattr(identity_photo, "_de_commons", lambda e: None)
    monkeypatch.setattr(
        "app.services.instagram.web_image.search",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no tocaba buscar en Google")),
    )
    monkeypatch.setattr(
        identity_guard, "verify_identity",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no tocaba mirar la foto")),
    )


def test_una_entidad_sin_identificar_no_recibe_foto(sin_fuentes):
    """La regla dura también aquí: publicar la cara de alguien de quien no
    sabemos quién es no es un riesgo menor por ser una foto bonita."""
    dudosa = ne.ResolvedEntity(ne.Mention("Guardiola", "person"), ne.AMBIGUOUS)
    assert identity_photo.find_for_entity(dudosa, TOPIC) is None


def test_la_ficha_propia_manda_sobre_todo_lo_demas(sin_fuentes):
    """Ya pasó `verify_provenance` en el cron y ya se ve en la web pública."""
    de_casa = ne.ResolvedEntity(
        ne.Mention("Extremoduro", "band", "", "subject"), ne.CORPUS,
        label="Extremoduro", image_url="https://res.cloudinary.com/x/extremoduro.jpg",
    )
    foto = identity_photo.find_for_entity(de_casa, TOPIC)
    assert foto.source == identity_photo.FICHA
    assert foto.verdict == "accredited"


def test_si_commons_no_acredita_no_se_publica_esa_foto(monkeypatch):
    """Y se sigue a Google: el paso 2 fallando no puede dar por perdida la foto."""
    monkeypatch.setattr(identity_photo, "_de_commons", lambda e: None)
    monkeypatch.setattr(
        "app.services.instagram.web_image.search",
        lambda *a, **k: [_cand(title="María Guardiola, política española", site="Wikipedia")],
    )
    monkeypatch.setattr(identity_photo, "_referencia", lambda e: None)
    monkeypatch.setattr(
        identity_guard, "verify_identity",
        lambda *a, **k: identity_guard.IdentityVerdict(True, "nada la contradice"),
    )
    foto = identity_photo.find_for_entity(PRESIDENTA, TOPIC)
    assert foto.source == identity_photo.GOOGLE
    assert foto.query == "María Guardiola política española"


def test_la_consulta_se_construye_de_la_entidad_no_del_titular():
    """El titular decía «Guardiola» a secas; el prompt añadía contexto inventado.
    Aquí la consulta sale del nombre y la descripción ya verificados."""
    assert identity_photo._consulta(PRESIDENTA) == "María Guardiola política española"
    assert "entrenador" not in identity_photo._consulta(PRESIDENTA)


def test_si_la_vision_dice_que_no_se_prueba_el_siguiente(monkeypatch):
    vistos = []
    monkeypatch.setattr(identity_photo, "_de_commons", lambda e: None)
    monkeypatch.setattr(identity_photo, "_referencia", lambda e: None)
    monkeypatch.setattr(
        "app.services.instagram.web_image.search",
        lambda *a, **k: [
            dict(_cand(title="María Guardiola, política española"), url="https://x/malo.jpg"),
            dict(_cand(title="María Guardiola, política española"), url="https://x/bueno.jpg"),
        ],
    )

    def _vision(url, **kw):  # noqa: ANN001, ANN003
        vistos.append(url)
        return identity_guard.IdentityVerdict("bueno" in url, "por el test")

    monkeypatch.setattr(identity_guard, "verify_identity", _vision)
    foto = identity_photo.find_for_entity(PRESIDENTA, TOPIC)
    assert foto.url.endswith("bueno.jpg")
    assert len(vistos) == 2


def test_si_ninguna_acredita_no_hay_foto(monkeypatch):
    monkeypatch.setattr(identity_photo, "_de_commons", lambda e: None)
    monkeypatch.setattr(identity_photo, "_referencia", lambda e: None)
    monkeypatch.setattr(
        "app.services.instagram.web_image.search",
        lambda *a, **k: [_cand(title="María Guardiola, política española")],
    )
    monkeypatch.setattr(
        identity_guard, "verify_identity",
        lambda *a, **k: identity_guard.IdentityVerdict(False, "es otra persona"),
    )
    assert identity_photo.find_for_entity(PRESIDENTA, TOPIC) is None


def test_un_candidato_que_no_pasa_el_filtro_no_gasta_una_llamada_de_vision(monkeypatch):
    """La visión cuesta dinero y tiempo. Y un stub que devolviera `[]` en vez de
    reventar dejaría pasar este test aunque se llamara."""
    monkeypatch.setattr(identity_photo, "_de_commons", lambda e: None)
    monkeypatch.setattr(
        "app.services.instagram.web_image.search",
        lambda *a, **k: [_cand(title="Pep Guardiola en el Etihad", site="Marca")],
    )
    monkeypatch.setattr(
        identity_guard, "verify_identity",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía mirarse")),
    )
    assert identity_photo.find_for_entity(PRESIDENTA, TOPIC) is None


# --- El gate de identidad ---------------------------------------------------- #
def test_sin_clave_pasa_pero_queda_marcado_para_revisar(monkeypatch):
    """Dar por buena una foto que nadie ha visto es como se publicó la de Pep."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    v = identity_guard.verify_identity("https://x/1.jpg", label="X", description="y")
    assert v.ok is True
    assert v.checked is False
    assert v.needs_human is True


def test_si_la_vision_falla_no_se_da_por_buena(monkeypatch):
    """Fail-safe, igual que `hero_guard`."""
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(identity_guard, "_b64", lambda url: "fake")
    monkeypatch.setattr(identity_guard, "_preguntar", lambda *a, **k: None)
    assert identity_guard.verify_identity("https://x/1.jpg", label="X").ok is False


def test_sin_referencia_se_pregunta_por_CONTRADICCION_no_por_reconocimiento(monkeypatch):
    """La distinción que sostiene el gate: un modelo no puede afirmar que una cara
    es la de una diputada que no ha visto nunca, y si se le pregunta así dice que
    sí a todo. Sí puede ver un banquillo y decir que no cuadra."""
    capturado = {}
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(identity_guard, "_b64", lambda url: "fake")

    def _espia(system, texto, imagenes):  # noqa: ANN001
        capturado["system"] = system
        return {"contradice": False, "motivo": "nada raro"}

    monkeypatch.setattr(identity_guard, "_preguntar", _espia)
    identity_guard.verify_identity("https://x/1.jpg", label="X", description="política")

    assert "CONTRADIGA" in capturado["system"]
    assert "no debes adivinarlo" in capturado["system"]


def test_con_referencia_si_se_comparan_las_dos_caras(monkeypatch):
    capturado = {}
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setattr(identity_guard, "_b64", lambda url: f"b64:{url}")

    def _espia(system, texto, imagenes):  # noqa: ANN001
        capturado["n"] = len(imagenes)
        return {"misma": True, "motivo": "mismos rasgos"}

    monkeypatch.setattr(identity_guard, "_preguntar", _espia)
    v = identity_guard.verify_identity(
        "https://x/1.jpg", label="X", reference_url="https://x/ref.jpg"
    )
    assert v.ok is True
    assert capturado["n"] == 2, "hay que mandarle las dos fotos"
