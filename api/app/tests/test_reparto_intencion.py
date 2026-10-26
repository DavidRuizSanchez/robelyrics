"""Reparto por intención, verso y entidad (26-10-2026).

Los casos son los que David encontró en el panel del blog. Las cifras de GSC son
literales de `data/gsc_page_queries.json` (2026-07-31..2026-10-23); los versos, de
la letra de «Jesucristo García» y de «La Hoguera» en la BD.
"""
from __future__ import annotations

from app.services import content_placement as cp
from app.services import verse_match as vm

GSC = {
    "/temas/religion": [
        {"query": "evaristo el rey de la baraja significado", "impressions": 150,
         "position": 6.7},
        {"query": "evaristo, el rey de la baraja significado", "impressions": 137,
         "position": 6.0},
    ],
    "/extremoduro/tu-en-tu-casa-nosotros-en-la-hoguera/jesucristo-garcia": [
        {"query": "evaristo el rey de la baraja significado", "impressions": 33,
         "position": 7.7},
    ],
    "/personas": [
        {"query": "integrantes de extremoduro", "impressions": 140, "position": 7.5},
    ],
}
JESUCRISTO = "/extremoduro/tu-en-tu-casa-nosotros-en-la-hoguera/jesucristo-garcia"
DISCO_HOGUERA = "/extremoduro/tu-en-tu-casa-nosotros-en-la-hoguera"

COMPOSICIONES = [
    vm.Composicion("jesucristo garcia", "Jesucristo García", (165, 14, 69),
                   ("soy evaristo el rey de la baraja", "cuanto mas necesito para ser dios")),
    vm.Composicion("la hoguera", "La Hoguera", (40,),
                   ("tu en tu casa nosotros en la hoguera",)),
    vm.Composicion("a", "A", (1,), ("y que no me da la gana de ir",)),
    vm.Composicion("b", "B", (2,), ("que no me da la vida",)),
]


def _verso(kw):
    v = vm.verso_de(kw, COMPOSICIONES)
    if not v:
        return None
    path = JESUCRISTO if v.clave == "jesucristo garcia" else f"/cancion/{v.clave}"
    return path, v.titulo, v.cita


def _titulo(kw):
    if "tu en tu casa nosotros en la hoguera" in kw.replace(",", ""):
        return DISCO_HOGUERA, "Tú en tu casa, nosotros en la hoguera"
    return None


def _entidad(kw):
    return ("/personas/ariel-rot", "Ariel Rot") if "ariel rot" in kw else None


def _repartir(keywords, *, semantica=None):
    return dict(cp.repartir(
        keywords, por_gsc=lambda kw: cp.dueno_gsc(GSC, kw), por_titulo=_titulo,
        por_semantica=semantica or (lambda texto: None), por_verso=_verso,
        por_entidad=_entidad))


# --- Intención ---------------------------------------------------------------- #
def test_la_misma_intencion_es_la_misma_clave():
    k = cp.clave_intencion
    assert k("ariel rot conciertos") == k("conciertos ariel rot") == \
        k("ariel rot conciertos 2026")
    assert k("ariel rot conciertos") != k("ariel rot discos")


def test_ariel_rot_las_tres_variantes_van_al_mismo_sitio():
    rutas = _repartir(["ariel rot conciertos", "conciertos ariel rot",
                       "ariel rot conciertos 2026"])
    assert {r.path for r in rutas.values()} == {"/personas/ariel-rot"}
    assert {r.via for r in rutas.values()} == {"entidad"}


def test_la_semantica_se_mide_sobre_la_intencion_entera():
    vistos = []

    def sem(texto):
        vistos.append(texto)
        return ("/temas/x", 0.7) if "·" in texto else None   # solo pasa con las dos

    rutas = _repartir(["fiesta pagana gira", "gira fiesta pagana"], semantica=sem)
    assert vistos == ["fiesta pagana gira · gira fiesta pagana"]
    assert {r.path for r in rutas.values()} == {"/temas/x"}


# --- Verso ------------------------------------------------------------------- #
def test_evaristo_va_a_la_cancion_y_la_evidencia_dice_que_es_canibalizacion():
    r = _repartir(["evaristo el rey de la baraja significado"])[
        "evaristo el rey de la baraja significado"]
    assert r.path == JESUCRISTO
    assert r.via == "verso"
    assert "Jesucristo García" in r.motivo
    assert "/temas/religion" in r.motivo and "canibalización" in r.motivo


def test_un_titulo_de_disco_manda_sobre_el_verso_que_lo_contiene():
    r = _repartir(["tu en tu casa nosotros en la hoguera"])[
        "tu en tu casa nosotros en la hoguera"]
    assert (r.path, r.via) == (DISCO_HOGUERA, "titulo")


def test_un_verso_que_esta_en_dos_canciones_no_decide():
    assert vm.verso_de("que no me da la", COMPOSICIONES) is None


def test_un_verso_sin_contenido_no_decide():
    assert vm.verso_de("y que no me", COMPOSICIONES) is None


def test_gsc_sigue_mandando_si_no_hay_cancion_ni_disco():
    r = _repartir(["integrantes de extremoduro"])["integrantes de extremoduro"]
    assert (r.path, r.via) == ("/personas", "gsc")


# --- Entidad ----------------------------------------------------------------- #
INDICE = [("ariel rot", "person", 3, "Ariel Rot"), ("leiva", "person", 4, "Leiva"),
          ("platero y tu", "band", 9, "Platero y Tú")]


def test_una_entidad_se_reconoce_como_palabras_enteras():
    assert cp.entidad_de("ariel rot conciertos", INDICE) == ("person", 3, "Ariel Rot")
    assert cp.entidad_de("leivano", INDICE) is None


def test_dos_entidades_no_deciden():
    assert cp.entidad_de("ariel rot y leiva", INDICE) is None


# --- Selector ---------------------------------------------------------------- #
def test_cubierto_por_el_cuerpo_dice_que_falta_metadata():
    pl = {"decision": "cubierto", "falta_meta": True,
          "candidates": [{"path": JESUCRISTO, "target": "ficha:1", "mergeable": True}]}
    assert "title/description" in cp.headline(pl)
    rec = [o["value"] for o in cp.selector_options(pl) if o["recommended"]]
    assert rec == ["skip"]
