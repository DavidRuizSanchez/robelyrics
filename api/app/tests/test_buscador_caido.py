"""Una caída del buscador no es «no encontrado» (18-11-2026).

DataForSEO devolvió 40101 (error interno) durante horas. `classify_fact` lo guardaba en
caché como `not_found` para siempre, y el fact-check, con una OBRA (`work_exists`),
convertía ese «no encontrado» en «refutado»: una caída podía desmentir un disco real.
"""
from __future__ import annotations


def test_una_busqueda_fallida_no_se_cachea(monkeypatch):
    from app.services import web_verify

    guardado: dict = {}
    monkeypatch.setattr(web_verify, "_load_cache", lambda: dict(guardado))
    monkeypatch.setattr(web_verify, "_save_cache", lambda c: guardado.update(c))

    def caida(query, wiki, estado=None):
        estado["fallo"] = True
        return ""

    monkeypatch.setattr(web_verify, "_gather_evidence", caida)
    r = web_verify.classify_fact("Destrozares se grabó en Berriz", query="x")
    assert r["verdict"] == "not_found" and r.get("sin_red") is True
    assert guardado == {}


def test_sin_resultados_de_verdad_si_se_cachea(monkeypatch):
    from app.services import web_verify

    guardado: dict = {}
    monkeypatch.setattr(web_verify, "_load_cache", lambda: dict(guardado))
    monkeypatch.setattr(web_verify, "_save_cache", lambda c: guardado.update(c))
    monkeypatch.setattr(web_verify, "_gather_evidence", lambda q, w, estado=None: "")
    r = web_verify.classify_fact("algo que nadie ha escrito", query="x")
    assert r["verdict"] == "not_found" and not r.get("sin_red")
    assert len(guardado) == 1


def test_con_la_web_caida_una_obra_no_se_refuta(monkeypatch):
    from app.services import fact_check

    monkeypatch.setattr("app.services.web_verify.classify_fact",
                        lambda text, **k: {"verdict": "not_found", "evidence": "", "source": "",
                                           "sin_red": True})
    claim = fact_check.Claim(type="work_exists", subject="Destrozares",
                             text="Robe publicó Destrozares", risk="high")
    v = fact_check._resolve_web(claim)
    assert v.status == "unverifiable" and v.source == "sin_red"
    assert fact_check.FactCheckReport(verdicts=[v]).to_review == []


def test_web_research_avisa_del_fallo(monkeypatch):
    from app.services import news_research

    monkeypatch.setenv("DATAFORSEO_LOGIN", "x")
    monkeypatch.setenv("DATAFORSEO_PASSWORD", "y")

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"tasks": [{"status_code": 40101, "status_message": "Internal SE Server Error.",
                               "result": None}]}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(news_research.httpx, "Client", _Client)
    estado: dict = {}
    assert news_research.web_research("x", estado=estado) == []
    assert estado.get("fallo") is True
