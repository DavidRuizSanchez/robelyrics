"""Seguimiento de fusiones: 4 semanas de después frente a 4 de antes (23-11-2026)."""
from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

from app.services import merge_watch as mw


def _q(query, position, impressions, clicks=0):
    return {"query": query, "position": position, "impressions": impressions,
            "clicks": clicks}


def test_las_ventanas_son_simetricas_y_sin_el_dia_del_cambio():
    antes, despues = mw.ventanas(datetime(2026, 10, 20, 6, 13, tzinfo=UTC))
    assert antes == (date(2026, 9, 22), date(2026, 10, 19))
    assert despues == (date(2026, 10, 21), date(2026, 11, 17))
    assert (antes[1] - antes[0]).days == (despues[1] - despues[0]).days == 27


def test_solo_se_mide_con_las_cuatro_semanas_de_despues_en_gsc():
    aplicada = date(2026, 10, 20)  # después acaba el 17-11; GSC va 3 días tarde
    assert not mw.lista_para_medir(aplicada, hoy=date(2026, 11, 19))
    assert mw.lista_para_medir(aplicada, hoy=date(2026, 11, 20))


def test_una_protegida_que_desaparece_se_avisa():
    # Antes la comparación saltaba en silencio lo que ya no aparecía.
    antes = [_q("de donde es extremoduro", 8.3, 356), _q("historia de extremoduro", 11.4, 7, 1)]
    res = mw.comparar(antes, [_q("historia de extremoduro", 11.0, 8)])
    assert [d["query"] for d in res["desaparecen"]] == ["de donde es extremoduro"]
    assert not res["caidas"]


def test_una_caida_de_mas_de_cinco_puestos_se_avisa_y_una_pequena_no():
    antes = [_q("a", 8.0, 50), _q("b", 8.0, 50)]
    res = mw.comparar(antes, [_q("a", 14.0, 30), _q("b", 12.0, 30)])
    assert [c["query"] for c in res["caidas"]] == ["a"]


def test_lo_que_no_estaba_protegido_no_cuenta():
    # Posición 40 sin clics no es una búsqueda que la página tenga que conservar.
    res = mw.comparar([_q("integrantes de extremoduro", 40.0, 30)], [])
    assert not res["caidas"] and not res["desaparecen"]


def test_el_correo_dice_las_ventanas_los_totales_y_los_retoques():
    opp = SimpleNamespace(path="/extremoduro",
                          applied_at=datetime(2026, 10, 20, 6, 13, tzinfo=UTC))
    inf = {"opp": opp,
           "ventanas": {"antes": ["2026-09-22", "2026-10-19"],
                        "despues": ["2026-10-21", "2026-11-17"]},
           "caidas": [], "desaparecen": [{"query": "x", "antes": 8.3,
                                          "impressions_antes": 40}],
           "objetivo": [{"query": "integrantes de extremoduro", "antes": None,
                         "despues": _q("integrantes de extremoduro", 42.0, 3)}],
           "pagina": {"antes": (10, 1000), "despues": (12, 900),
                      "sitio_antes": (1000, 50000), "sitio_despues": (900, 40000)},
           "retoques": ["19-11-2026 (fusión)"]}
    asunto, texto = mw.texto_informe([inf], "https://entreinteriores.com")
    assert asunto.startswith("⚠️")
    assert "antes 2026-09-22..2026-10-19 · después 2026-10-21..2026-11-17" in texto
    assert "10 → 12 clics (+20 %)" in texto
    assert "todo el sitio, mismas fechas: 1000 → 900 clics (-10 %)" in texto
    assert "desaparece «x»" in texto
    assert "«integrantes de extremoduro»: antes no aparece; después pos 42.0" in texto
    assert "se volvió a tocar" in texto


def test_las_que_mas_pierden_dicen_si_es_posicion_o_demanda():
    # Caso real de /extremoduro (fusión del 20-10): misma posición, menos búsquedas.
    antes = [_q("extremoduro de donde son", 9.9, 89), _q("extremoduro genero", 5.6, 37)]
    despues = [_q("extremoduro de donde son", 10.1, 29), _q("extremoduro genero", 5.5, 26)]
    res = mw.comparar(antes, despues)
    assert res["pierden"][0] == {"query": "extremoduro de donde son", "delta": -60,
                                 "antes": 9.9, "ahora": 10.1}
    assert not res["caidas"]
