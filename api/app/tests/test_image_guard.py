"""Tests de la guarda de imágenes: nada de fotos rotas ni de fotos de otro.

Cada caso de aquí es un fallo REAL encontrado en el site (jul-2026), no un ejemplo
inventado. Son la red que evita que vuelvan, que es justo lo que faltaba: el remedio
(`--rehost`) existía, pero como nadie vigilaba, el problema regresaba solo.

Sin red: la evidencia de Commons se inyecta.
"""
from __future__ import annotations

import pytest

from app.services import image_guard as ig

_WIKI = "https://upload.wikimedia.org/wikipedia/commons/2/29/KutxiRomero.jpg"
_CLOUD = "https://res.cloudinary.com/ddnkzrplj/image/upload/v1780475180/entreinteriores-art/x.jpg"


@pytest.fixture
def commons(monkeypatch):
    """Permite fijar lo que Commons dice de un fichero."""
    def _set(categories=(), description=""):
        monkeypatch.setattr(ig, "commons_evidence", lambda *a, **k: {
            "categories": list(categories), "description": description, "missing": False,
        })
    return _set


# --- Alojamiento: nada que dependa de un tercero ---------------------------- #
def test_una_url_de_wikimedia_hay_que_traersela():
    assert ig.must_rehost(_WIKI) is True
    assert ig.hotlinks_a_tercero(_WIKI) is True


def test_lo_nuestro_y_lo_local_no_se_toca():
    assert ig.must_rehost(_CLOUD) is False
    assert ig.must_rehost("/album-covers/deltoya.jpg") is False


def test_se_reconoce_el_fichero_de_commons_en_ambas_formas():
    assert ig.commons_filename(_WIKI) == "KutxiRomero.jpg"
    assert ig.commons_filename(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d9/Le%C3%B1o_en_1981.jpg/1280px-x.jpg"
    ) == "Leño_en_1981.jpg"
    assert ig.commons_filename(
        None, "https://commons.wikimedia.org/wiki/File:Barricada_Extremusika_2006.jpg"
    ) == "Barricada_Extremusika_2006.jpg"
    assert ig.commons_filename(_CLOUD) is None


# --- Acreditación: ¿la fuente dice que son ellos? --------------------------- #
def test_commons_acredita_al_grupo(commons):
    """Caso Los Enemigos: el fichero se llama «San Isidro 2017…», pero Commons lo
    categoriza como Los Enemigos. La foto es legítima: manda la categoría, no el
    nombre del fichero."""
    commons(categories=["Fiestas de San Isidro 2017 in Madrid", "Los Enemigos",
                        "Music events in Madrid"],
            description="La música tomó las calles en la primera noche de San Isidro")
    v = ig.verify_provenance(entity_name="Los Enemigos", image_url=_WIKI)
    assert v.status == "accredited" and v.publishable


def test_foto_de_prensa_sin_fuente_va_a_revision():
    """Caso Rebrote: foto de prensa en Cloudinary con un crédito escrito a mano.
    Nadie acredita que sean ellos, pero tampoco se borra sola (podría ser el logo
    oficial de un sello): la decide un humano."""
    v = ig.verify_provenance(
        entity_name="Rebrote", image_url=_CLOUD, attribution="Promo Rebrote 2025")
    assert v.status == "unverifiable"
    assert not v.publishable and v.needs_human


def test_una_foto_realojada_con_licencia_cc_se_conserva():
    """Regresión: al re-alojar en Cloudinary se perdía el fichero de origen, y el
    guard penalizaba justo a las que YA se habían arreglado. Con autor y licencia
    hay traza suficiente para conservarlas."""
    v = ig.verify_provenance(
        entity_name="Marea", image_url=_CLOUD,
        attribution="Libertinus Yomango · Wikimedia Commons (CC BY-SA 2.0)", license_="CC")
    assert v.status == "legacy_cc" and v.publishable


def test_el_arte_propio_se_publica_porque_no_afirma_ser_nadie():
    v = ig.verify_provenance(
        entity_name="Ñu", image_url=_CLOUD,
        attribution="Arte generado por IA · Entre Interiores", license_="propio")
    assert v.status == "own_art" and v.publishable


def test_un_apodo_corto_no_acredita_sin_contexto_musical(commons):
    """Caso Salo (batería de Extremoduro): su foto era de «Salo (food) in Ukraine»,
    tocino ucraniano. Un nombre de una palabra casa con cualquier cosa."""
    commons(categories=["Salo (food) in Ukraine", "PD-self", "Taken with Nikon D50"],
            description="Salo with pepper, closeup")
    v = ig.verify_provenance(entity_name="Salo", image_url=_WIKI)
    assert v.status == "unaccredited"
    assert not v.publishable and v.needs_human


def test_un_apodo_corto_si_acredita_con_contexto_musical(commons):
    commons(categories=["Extremoduro", "Iñaki Antón"],
            description="Uoho tocando con Extremoduro en la gira de 2014")
    v = ig.verify_provenance(entity_name="Uoho", image_url=_WIKI)
    assert v.status == "accredited" and v.publishable


def test_el_homonimo_extranjero_va_a_revision_no_a_la_basura(commons):
    """Caso Fito Cabrales / Fito Páez y Los Niños de los Ojos Rojos (los mexicanos):
    el nombre casa pero la foto es de otro país. Ni se publica ni se borra sola."""
    commons(categories=["Fito Páez", "Files from Ministerio de Cultura de la Nación Argentina"],
            description="Buenos Aires, el músico Fito Páez brindó un concierto gratuito")
    v = ig.verify_provenance(entity_name="Fito", image_url=_WIKI)
    assert v.status == "homonym_risk"
    assert not v.publishable and v.needs_human


def test_el_nombre_de_pila_tambien_acredita(commons):
    """Commons etiqueta a unos por el nombre artístico y a otros por el de pila."""
    commons(categories=["Iñaki Antón", "Extremoduro"], description="Concierto de 2014")
    v = ig.verify_provenance(entity_name="Uoho", aliases=["Iñaki Antón"], image_url=_WIKI)
    assert v.publishable


def test_sin_nombre_no_se_desacredita_nada(commons):
    """Regresión: leer `Person.name` (que no existe) dejaba el nombre vacío y
    marcaba TODAS las fotos de personas como no acreditadas. Con --retire eso
    habría borrado fotos legítimas del site."""
    commons(categories=["Kutxi Romero"], description="Kutxi Romero, Marea, 2007")
    v = ig.verify_provenance(entity_name="", image_url=_WIKI)
    assert v.status == "unknown"
    assert not v.publishable          # no se publica…
    assert v.status != "unaccredited"  # …pero tampoco se retira


def test_los_articulos_no_cuentan_para_acreditar(commons):
    """«Los Enemigos» no puede darse por acreditado solo porque aparezca «los»."""
    commons(categories=["Los Ramones", "Music"], description="banda de rock")
    v = ig.verify_provenance(entity_name="Los Enemigos", image_url=_WIKI)
    assert not v.publishable


def test_sin_imagen_no_hay_veredicto():
    assert ig.verify_provenance(entity_name="X", image_url=None).status == "unknown"


def test_si_commons_no_responde_no_se_acredita(monkeypatch):
    """Sin red no se publica: el silencio no es una acreditación."""
    monkeypatch.setattr(ig, "commons_evidence", lambda *a, **k: {})
    v = ig.verify_provenance(entity_name="Leño", image_url=_WIKI)
    assert v.status == "unaccredited" and not v.publishable


def test_una_categoria_dedicada_acredita_aunque_el_nombre_sea_de_una_palabra(commons):
    """Regresión: «Rosendo» y «Barricada» tienen categoría propia en Commons pero
    sus ficheros no hablan de música; con la regla del apodo corto se habrían
    retirado fotos correctas."""
    commons(categories=["Rosendo", "People of Spain in 2012", "CC-BY-SA-3.0"],
            description="Figura de Rosendo en el museu del rock")
    v = ig.verify_provenance(entity_name="Rosendo", image_url=_WIKI)
    assert v.status == "accredited" and v.publishable


def test_nada_se_retira_por_no_encontrar_el_nombre(commons):
    """A Leiva lo escriben «Leyva» en Commons: no encontrar el nombre NO prueba que
    la foto sea de otro, así que va a revisión, nunca a la papelera."""
    commons(categories=["All media supported by Wikimedia España in 2026", "Extracted images"],
            description="Premios Goya 2026")
    v = ig.verify_provenance(entity_name="Leiva", image_url=_WIKI)
    assert not v.publishable
    assert v.needs_human  # a la cola de erratas, no a la papelera


def test_el_autor_de_la_imagen_no_acredita_su_contenido(commons):
    """Caso real: «Francisco de Miranda by Lorenzo Gonzalez, 1977» se aceptó como
    retrato de Lorenzo González. El nombre casaba como AUTOR de la obra, no como
    la persona retratada."""
    commons(categories=["Paintings in Philadelphia", "PD-old"],
            description="Francisco de Miranda by Lorenzo Gonzalez, 1977, Philadelphia")
    v = ig.verify_provenance(entity_name="Lorenzo González", image_url=_WIKI)
    assert not v.publishable


def test_el_credito_fotografico_tampoco_acredita(commons):
    commons(categories=["Concerts in Madrid"], description="Foto: Manolo Chinato, 2015")
    v = ig.verify_provenance(entity_name="Manolo Chinato", image_url=_WIKI)
    assert not v.publishable


def test_una_descripcion_normal_sigue_acreditando(commons):
    """El filtro anti-autoría no puede cargarse las descripciones buenas."""
    commons(categories=["Rosendo"], description="Leño playing live on 28 August 1981")
    assert ig.verify_provenance(entity_name="Leño", image_url=_WIKI).publishable


# --- Obra gráfica propia (infografías del estudio de repertorio) ------------ #
# El hueco era real: la única puerta de arte propio exigía literalmente
# «generado por IA», así que una infografía hecha a mano y alojada por nosotros
# caía a `unsourced` → `needs_human`, y el cron de las 04:40 abría una errata
# contra ella cada noche.
def test_una_infografia_propia_es_obra_propia_y_se_publica():
    v = ig.verify_provenance(
        entity_name="Extremoduro",
        image_url=_CLOUD,
        attribution="Entre Interiores · entreinteriores.com",
        license_="propio",
    )
    assert v.status == "own_art"
    assert v.publishable is True
    assert v.needs_human is False


def test_basta_la_licencia_propio_sin_mencionar_la_casa():
    v = ig.verify_provenance(
        entity_name="Extremoduro", image_url=_CLOUD,
        attribution="Gráfico del estudio del repertorio", license_="propio",
    )
    assert v.status == "own_art"


def test_una_url_ajena_no_se_declara_obra_propia_por_mucho_que_lo_diga_el_credito():
    """La puerta exige host propio. Si no, cualquier foto de un tercero entraría
    con solo escribirle «Entre Interiores» en el crédito."""
    v = ig.verify_provenance(
        entity_name="Rosendo",
        image_url="https://un-medio-cualquiera.es/foto-de-rosendo.jpg",
        attribution="Entre Interiores", license_="propio",
    )
    assert v.status != "own_art"
    assert v.publishable is False


def test_una_foto_realojada_con_su_autor_sigue_siendo_legacy_cc_no_obra_propia():
    """La ampliación no se puede comer el caso de al lado: lo re-alojado desde
    Commons conserva autor y licencia libre, y tiene su propio estado."""
    v = ig.verify_provenance(
        entity_name="Kutxi Romero", image_url=_CLOUD,
        attribution="Foto de un tercero (Wikimedia Commons)", license_="CC BY-SA 4.0",
    )
    assert v.status == "legacy_cc"


def test_el_criterio_de_obra_propia_no_puede_divergir_del_de_hero_guard():
    """Dos sitios deciden si una pieza es «de la casa»: esta guarda y el gate
    del hero. Vivían con el vocabulario duplicado, que es como se desincronizan
    (misma lección que `captions_moldes.QUESTIONS` vs `tono_guard`). Si alguien
    cambia uno, este test cae."""
    from app.services import hero_guard as hg

    casos = [
        {"attribution": "Entre Interiores · entreinteriores.com", "license": "propio"},
        {"attribution": "Entre Interiores", "license": None},
        {"attribution": "Gráfico del estudio", "license": "propio"},
        {"attribution": "Foto de agencia", "license": "todos los derechos"},
        {"attribution": "", "license": ""},
    ]
    for caso in casos:
        mio = ig.es_obra_propia(caso["attribution"], caso["license"])
        suyo = hg._is_trusted(caso)
        assert mio == suyo, f"divergen en {caso}: image_guard={mio} hero_guard={suyo}"
