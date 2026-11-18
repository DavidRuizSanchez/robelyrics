"""Seguimiento de los headings humanizados: ventanas, grupos y consultas protegidas."""
from datetime import date

from app.services import seguimiento_headings as sh

CAMBIOS = {
    "/grupos/barricada": {"primero": "2026-11-10T21:30:00+00:00",
                          "ultimo": "2026-11-11T10:00:00+00:00", "tipo": "band"},
    "/personas/diego-garay": {"primero": "2026-11-11T09:00:00+00:00",
                              "ultimo": "2026-11-11T09:00:00+00:00", "tipo": "person"},
}


def test_ventanas_simetricas_sin_los_dias_del_cambio():
    antes, despues = sh.ventanas("2026-11-10", "2026-11-11", 1)
    assert antes == (date(2026, 11, 3), date(2026, 11, 9))
    assert despues == (date(2026, 11, 12), date(2026, 11, 18))
    antes, despues = sh.ventanas("2026-11-11", "2026-11-11", 4)
    assert (antes[1] - antes[0]).days + 1 == 28
    assert (despues[1] - despues[0]).days + 1 == 28


def test_la_semana_solo_sale_con_los_datos_completos():
    assert not sh.semana_cubierta(CAMBIOS, "2026-11-17", 1)
    assert sh.semana_cubierta(CAMBIOS, "2026-11-18", 1)
    assert sh.semana_pendiente(CAMBIOS, "2026-11-18", {}) == 1
    assert sh.semana_pendiente(CAMBIOS, "2026-11-18", {"1": "x"}) is None
    # La Mac dormida no se salta semanas: sale la primera que falta.
    assert sh.semana_pendiente(CAMBIOS, "2026-12-30", {"1": "x"}) == 2
    assert sh.semana_pendiente(CAMBIOS, "2026-12-30", {str(k): "x" for k in sh.SEMANAS}) is None


def _gsc():
    pd = [
        # cambiada: antes (03..09) y después (12..18); el 10 y el 11 no cuentan
        ["/grupos/barricada", "2026-11-05", 4, 100, 8.0],
        ["/grupos/barricada", "2026-11-10", 50, 500, 1.0],
        ["/grupos/barricada", "2026-11-13", 6, 120, 6.0],
        ["/personas/diego-garay", "2026-11-06", 1, 30, 12.0],
        ["/personas/diego-garay", "2026-11-14", 0, 10, 15.0],
        # control: mismas ventanas globales
        ["/blog/x", "2026-11-04", 10, 200, 5.0],
        ["/blog/x", "2026-11-15", 10, 200, 5.0],
        # fuera de toda ventana
        ["/blog/x", "2026-10-01", 99, 999, 1.0],
    ]
    pqd = [
        ["/grupos/barricada", "barricada grupo", "2026-11-05", 2, 40, 4.0],
        ["/grupos/barricada", "barricada grupo", "2026-11-13", 1, 40, 12.0],
        ["/grupos/barricada", "el drogas", "2026-11-05", 1, 10, 9.0],
        ["/grupos/barricada", "el drogas", "2026-11-13", 1, 10, 8.0],
        ["/personas/diego-garay", "diego garay", "2026-11-06", 1, 5, 3.0],
        ["/personas/diego-garay", "lejos", "2026-11-06", 0, 5, 40.0],  # no protegida
    ]
    insp = {"/grupos/barricada": {"lastCrawlTime": "2026-11-12T08:00:00Z"},
            "/personas/diego-garay": {"lastCrawlTime": "2026-11-02T08:00:00Z"}}
    return {"page_daily": pd, "page_query_daily": pqd, "inspeccion": insp, "fin": "2026-11-18"}


def test_grupos_y_dias_del_cambio_fuera():
    res = sh.analizar(CAMBIOS, _gsc(), 1)
    cam, con = res["grupos"]["cambiadas"], res["grupos"]["control"]
    assert (cam.antes.clics, cam.despues.clics) == (5, 6)  # el 10-11 (50 clics) no cuenta
    assert cam.antes.impresiones == 130
    assert round(cam.antes.posicion, 2) == round((8 * 100 + 12 * 30) / 130, 2)
    assert (con.antes.clics, con.despues.clics) == (10, 10)
    assert cam.paginas == 2 and con.paginas == 1


def test_rastreo_separa_lo_que_google_aun_no_ha_visto():
    res = sh.analizar(CAMBIOS, _gsc(), 1)
    assert res["rastreo"] == {"inspeccionadas": 2, "tras_el_cambio": 1, "antes_del_cambio": 1}
    assert res["grupos"]["rastreadas"].despues.clics == 6
    assert res["grupos"]["sin_rastrear"].antes.clics == 1


def test_consultas_protegidas_como_ranking_guard():
    res = sh.analizar(CAMBIOS, _gsc(), 1)
    por_q = {p["query"]: p for p in res["protegidas"]}
    assert "lejos" not in por_q  # sin clics y en pos. 40
    assert por_q["barricada grupo"]["estado"] == "cae"
    assert por_q["barricada grupo"]["delta"] == 8.0
    assert por_q["el drogas"]["estado"] == "estable"
    assert por_q["diego garay"]["estado"] == "sin datos después"


def test_informe_cita_fuentes_y_marca_la_hipotesis():
    res = sh.analizar(CAMBIOS, _gsc(), 1)
    texto = sh.informe_texto(res, {"site": "sc-domain:entreinteriores.com", "fin": "2026-11-18",
                                   "fetched_at": "2026-11-21T08:00:00+00:00",
                                   "primer_cambio": "2026-11-10",
                                   "ultimo_cambio": "2026-11-11"})
    assert "[HIPÓTESIS]" in texto
    assert "content_revisions" in texto and "Search Analytics" in texto
    assert "«barricada grupo»" in texto
    assert "semana 1/4" in sh.asunto(res)


def test_seguimiento_conjunto_aparta_lo_que_cambio_de_title():
    """David, 11-11-2026: titles por tandas y seguimiento conjunto. Barricada cambia
    de title el 13-11, dentro de su «después» de la semana 1: ya no mide solo los
    headings. Diego Garay cambia el 01-12, fuera de esa ventana: sigue contando.
    /blog/x (control) cambia el 14-11: deja de servir de control."""
    titles = {"/grupos/barricada": "2026-11-13T05:00:00+00:00",
              "/personas/diego-garay": "2026-12-01T05:00:00+00:00",
              "/blog/x": "2026-11-14T05:00:00+00:00"}
    res = sh.analizar(CAMBIOS, _gsc(), 1, titles)
    cam, con = res["grupos"]["cambiadas"], res["grupos"]["control"]
    assert res["apartadas_title"] == {"cambiadas": 1, "control": 1, "simultaneas": 0}
    assert cam.paginas == 1 and (cam.antes.clics, cam.despues.clics) == (1, 0)
    assert con.paginas == 0
    assert all(p["path"] != "/grupos/barricada" for p in res["protegidas"])
    assert any("Apartadas por tener el title nuevo" in x for x in sh.lectura(res))
    # A 4 semanas, Diego Garay también queda dentro de su ventana y se aparta.
    assert sh.apartadas_por_title(CAMBIOS, titles, 4)[0] == {"/grupos/barricada",
                                                             "/personas/diego-garay"}


def test_title_cambiado_a_la_vez_que_los_headings_cuenta_como_cambio_conjunto():
    """11-11-2026: las 270 páginas de titles se rehicieron el día siguiente a los
    headings. Apartarlas vaciaba el informe; se miden juntas y se dice."""
    titles = {"/grupos/barricada": "2026-11-12T05:00:00+00:00",   # ultimo 11-11 + 1 día
              "/personas/diego-garay": "2026-11-11T20:00:00+00:00",
              "/blog/x": "2026-11-11T20:00:00+00:00"}               # control: fuera
    res = sh.analizar(CAMBIOS, _gsc(), 1, titles)
    assert res["apartadas_title"] == {"cambiadas": 0, "control": 1, "simultaneas": 2}
    assert res["grupos"]["cambiadas"].paginas == 2
    assert res["grupos"]["control"].paginas == 0
    assert any("CONJUNTO" in x for x in sh.lectura(res))
    assert sh.informe_texto(res, {}).startswith("HEADINGS Y TITLES HUMANOS")
    assert res["grupos"]["headings_y_title"].paginas == 2
    assert res["grupos"]["solo_headings"].paginas == 0


def test_sin_titles_el_informe_no_cambia():
    assert sh.analizar(CAMBIOS, _gsc(), 1, None)["grupos"]["cambiadas"].paginas == 2
