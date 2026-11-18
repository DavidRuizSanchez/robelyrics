"""Guardas del descubrimiento de relaciones (plan de relaciones, 18-11-2026)."""
from scripts.relaciones.descubrir import INTERNOS, _mb, _qid, _rol, es_lugar
from scripts.relaciones.identidades import _norm


def _ent(**claims):
    return {"claims": {p: [{"mainsnak": {"datavalue": {"value": {"id": v}}}} for v in vs]
                       for p, vs in claims.items()}}


def test_una_manzana_no_es_un_lugar():
    """La Fuga declaraba P740 = «Reineta Panera» (Q96627233), una variedad de manzana."""
    assert not es_lugar(_ent(P31=["Q101815"]), "Q96627233")


def test_un_pais_no_es_un_lugar_de_nacimiento():
    """Cantera declaraba P19 = España: un país no dice dónde nació nadie."""
    assert not es_lugar(_ent(P17=["Q29"], P31=["Q6256"]), "Q29")


def test_una_ciudad_si_es_un_lugar():
    bilbao = _ent(P17=["Q29"], P31=["Q2074737"])
    assert es_lugar(bilbao, "Q8692")


def test_robe_y_extremoduro_no_salen_como_nodo_literal():
    """Su formación manda en band_memberships: un «Robe» sin @id duplicaría al artista."""
    assert {"Q2311472", "Q123516175"} <= INTERNOS


def test_identificadores_de_las_urls():
    assert _qid("https://www.wikidata.org/wiki/Q263632") == "Q263632"
    assert _mb("https://musicbrainz.org/release-group/2d9dcaa2-fb3f-3fbd-a62d-d2f4094adf5b") == (
        "release-group", "2d9dcaa2-fb3f-3fbd-a62d-d2f4094adf5b")


def test_el_rol_de_musicbrainz_sale_en_espanol():
    assert _rol(["lead vocals", "original"]) == "voz, miembro original"


def test_el_nombre_se_compara_sin_tildes_ni_mayusculas():
    assert _norm("  Juantxu  Olano ") == _norm("juantxu olano")
    assert _norm("Cáceres") == _norm("caceres")
