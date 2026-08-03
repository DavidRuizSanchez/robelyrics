"""Tests del volcado de queries por URL desde GSC.

Lo que blindan: que un token caducado NO borre el último volcado bueno. Pasó de
verdad el 03-08-2026 — el `refresh_token` estaba revocado, GSC devolvía cero
filas, el job escribía `"pages": {}` y salía con código 0, así que el
`gsc_weekly.sh` seguía adelante y rsynceaba el fichero vacío a producción. El
diagnóstico de páginas se quedó sin la única señal de posición REAL que hay.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.seo import gsc_fetch_page_queries as fetch


def _correr(monkeypatch, out: Path, filas: list[dict], argv_extra: list[str] | None = None):
    monkeypatch.setattr(fetch.gsc_client, "is_configured", lambda: True)
    monkeypatch.setattr(fetch.gsc_client, "page_query_rows", lambda *a, **k: filas)
    monkeypatch.setattr(fetch.gsc_client, "SITE_URL", "sc-domain:entreinteriores.com",
                        raising=False)
    monkeypatch.setattr(
        "sys.argv",
        ["gsc_fetch_page_queries", "--weeks", "12", "--out", str(out), *(argv_extra or [])],
    )
    fetch.main()


def _fila(page: str, query: str) -> dict:
    return {"keys": [page, query], "impressions": 6, "clicks": 0,
            "position": 8.0, "ctr": 0.0}


def test_un_volcado_vacio_no_machaca_el_anterior(monkeypatch, tmp_path):
    """Cero páginas → ni se escribe ni se sale con 0: el .sh tiene que cortar."""
    out = tmp_path / "gsc_page_queries.json"
    bueno = {"site": "sc-domain:entreinteriores.com",
             "period": {"start": "2026-04-26", "end": "2026-07-19"},
             "pages": {"/extremoduro/agila": [{"query": "agila contraportada",
                                               "impressions": 6, "clicks": 0,
                                               "position": 8.0, "ctr": 0.0}]}}
    out.write_text(json.dumps(bueno), encoding="utf-8")

    with pytest.raises(SystemExit) as e:
        _correr(monkeypatch, out, filas=[])

    assert e.value.code == 1
    assert json.loads(out.read_text(encoding="utf-8")) == bueno


def test_con_datos_escribe_los_dos_formatos(monkeypatch, tmp_path):
    out = tmp_path / "gsc_page_queries.json"
    _correr(monkeypatch, out, filas=[
        _fila("https://entreinteriores.com/extremoduro/agila", "agila contraportada"),
        _fila("https://entreinteriores.com/extremoduro/agila", "agila portada"),
    ])

    data = json.loads(out.read_text(encoding="utf-8"))
    assert list(data["pages"]) == ["/extremoduro/agila"]
    assert len(data["pages"]["/extremoduro/agila"]) == 2
    # el formato plano que lee keyword_research._gsc_queries
    plano = json.loads((tmp_path / "gsc_queries.json").read_text(encoding="utf-8"))
    assert {q["query"] for q in plano} == {"agila contraportada", "agila portada"}


def test_permitir_vacio_es_la_valvula_para_un_sitio_nuevo(monkeypatch, tmp_path):
    out = tmp_path / "gsc_page_queries.json"
    _correr(monkeypatch, out, filas=[], argv_extra=["--permitir-vacio"])

    assert json.loads(out.read_text(encoding="utf-8"))["pages"] == {}
