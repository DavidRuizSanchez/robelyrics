"""La formación de un grupo enlaza a sus miembros por IDENTIDAD (18-11-2026).

`bands.members` es una lista de nombres. Enlazarla por nombre suelto es el camino de
los homónimos (Fito Páez por Fito Cabrales), así que solo se enlaza a quien tiene una
relación de pertenencia VERIFICADA con ese grupo y ficha publicada.
"""
from __future__ import annotations

from app.db.models import Band, Person
from app.routers.public import _rutas_de_miembros
from app.services import link_policy
from app.tests.test_relations import _ficha, _guardar, _p, cat, db  # noqa: F401

T1 = [{"kind": "creditos_disco", "tier": "T1", "evidencia": "libreto"}]


def _barricada(cat):  # noqa: F811
    drogas = Person(slug="enrique-el-drogas", stage_name="El Drogas", full_name="Enrique Villarreal")
    rosendo = Person(slug="rosendo-mercado", stage_name="Rosendo", full_name="Rosendo Mercado Ruiz")
    banda = Band(slug="barricada", name="Barricada", kind="band",
                 members=[{"name": "El Drogas"}, {"name": "Boni"}, {"name": "Rosendo Mercado"}])
    cat.add_all([drogas, rosendo, banda])
    cat.flush()
    for tipo, ident, slug in (("person", drogas.id, drogas.slug), ("person", rosendo.id, rosendo.slug),
                              ("band", banda.id, banda.slug)):
        _ficha(cat, tipo, ident, slug)
    cat.commit()
    return banda


def test_solo_enlaza_lo_verificado(cat):  # noqa: F811
    banda = _barricada(cat)
    _guardar(cat, _p("person:enrique-el-drogas", "memberOf", "band:barricada",
                     estado="verificada", verificado_por="david", fuentes=T1))
    # Rosendo con la relación solo PENDIENTE: se nombra, no se enlaza.
    _guardar(cat, _p("person:rosendo-mercado", "memberOf", "band:barricada"))
    rutas = _rutas_de_miembros(cat, banda, ["El Drogas", "Boni", "Rosendo Mercado"])
    assert rutas == {"El Drogas": "/personas/enrique-el-drogas"}


def test_principio_del_nombre_completo(cat):  # noqa: F811
    banda = _barricada(cat)
    _guardar(cat, _p("person:rosendo-mercado", "memberOf", "band:barricada",
                     estado="verificada", verificado_por="david", fuentes=T1))
    assert _rutas_de_miembros(cat, banda, ["Rosendo Mercado"]) == {
        "Rosendo Mercado": "/personas/rosendo-mercado"}
    # «Rosendo M» no es el principio de una palabra completa.
    assert _rutas_de_miembros(cat, banda, ["Rosendo M"]) == {}


def test_la_plantilla_del_grupo_cuenta_la_formacion(cat):  # noqa: F811
    banda = _barricada(cat)
    _guardar(cat, _p("person:enrique-el-drogas", "memberOf", "band:barricada",
                     estado="verificada", verificado_por="david", fuentes=T1))
    rutas = link_policy.rutas_de_nodos(cat)
    assert "/personas/enrique-el-drogas" in link_policy.plantilla_de(cat, "band", banda.id, rutas)
