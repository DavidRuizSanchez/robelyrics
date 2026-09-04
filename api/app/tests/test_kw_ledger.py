"""Tests del control de gasto del motor de keyword research.

Lo que blindan: que trocear una ola no destruya datos ni descontrole el
presupuesto. Los tres agujeros eran del mismo tipo — el motor se creía siempre en
su primera ejecución:

- el tope de gasto arrancaba a cero en cada proceso, así que cinco tandas con
  `--max-spend 40` podían gastar $200 sin que saltara nada;
- `master.csv` se abría en modo `"w"` y la segunda tanda truncaba lo de la
  primera, dejando a `kw_merge` un universo mutilado en silencio;
- los errores «sin respuesta» no se cacheaban (bien) pero tampoco se recordaban
  (mal), así que la misma semilla rota se repagaba en cada ronda. En la ola 1
  fueron 294 de 1.144 llamadas pagadas.
"""
from __future__ import annotations

import json

from app.services.kw_cache import RunPaths, SpendLedger


def _paths(tmp_path) -> RunPaths:
    p = RunPaths(root=tmp_path, run_id="ola-test")
    p.ensure()
    return p


def _linea(cost: float, *, from_cache: bool = False) -> str:
    return json.dumps({"provider": "dataforseo", "endpoint": "x",
                       "cost_usd": cost, "units": 0, "from_cache": from_cache})


def test_el_gasto_previo_se_rehidrata(tmp_path):
    """Segunda tanda: el tope cuenta desde lo ya gastado, no desde cero."""
    paths = _paths(tmp_path)
    paths.ledger_path.write_text("\n".join(_linea(3.0) for _ in range(4)),
                                 encoding="utf-8")

    led = SpendLedger(paths=paths, max_spend_usd=40.0, max_ahrefs_units=1000)

    assert led.spent_usd == 12.0
    assert led.calls == 4


def test_lo_servido_de_cache_no_cuenta_como_gasto(tmp_path):
    paths = _paths(tmp_path)
    paths.ledger_path.write_text(
        "\n".join([_linea(2.0), _linea(0.0, from_cache=True), _linea(0.0, from_cache=True)]),
        encoding="utf-8",
    )

    led = SpendLedger(paths=paths, max_spend_usd=40.0, max_ahrefs_units=1000)

    assert led.spent_usd == 2.0
    assert led.calls == 1


def test_el_tope_salta_contando_lo_de_la_tanda_anterior(tmp_path):
    """El caso que motivó todo: sin esto, cada tanda tenía el tope entero."""
    import pytest
    from app.services.kw_cache import BudgetExceeded

    paths = _paths(tmp_path)
    paths.ledger_path.write_text(_linea(9.5), encoding="utf-8")

    led = SpendLedger(paths=paths, max_spend_usd=10.0, max_ahrefs_units=1000)

    with pytest.raises(BudgetExceeded):
        led.gate(est_cost_usd=1.0)


def test_una_linea_corrupta_no_invalida_la_cuenta(tmp_path):
    paths = _paths(tmp_path)
    paths.ledger_path.write_text(f"{_linea(1.0)}\n{{rota\n{_linea(2.0)}\n",
                                 encoding="utf-8")

    led = SpendLedger(paths=paths, max_spend_usd=40.0, max_ahrefs_units=1000)

    assert led.spent_usd == 3.0


def test_sin_ledger_previo_arranca_a_cero(tmp_path):
    led = SpendLedger(paths=_paths(tmp_path), max_spend_usd=40.0, max_ahrefs_units=1000)

    assert led.spent_usd == 0.0
    assert led.calls == 0


def test_se_puede_desactivar_la_rehidratacion(tmp_path):
    paths = _paths(tmp_path)
    paths.ledger_path.write_text(_linea(99.0), encoding="utf-8")

    led = SpendLedger(paths=paths, max_spend_usd=40.0, max_ahrefs_units=1000,
                      rehidratar=False)

    assert led.spent_usd == 0.0
