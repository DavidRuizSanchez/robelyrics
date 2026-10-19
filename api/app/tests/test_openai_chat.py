"""Tests de `openai_chat_kwargs`, el único sitio que decide qué parámetros llegan a OpenAI.

Cada caso es una combinación que la API rechaza con un 400 si se arma mal
(comprobado contra la API real el 19-10-2026):

- gpt-6-luna sin `reasoning_effort` razona en `medium` y rechaza `temperature`.
- gpt-6-luna con un effort distinto de `none` rechaza `temperature`.
- gpt-6-luna rechaza `max_tokens`; va `max_completion_tokens`.
- gpt-4o rechaza `reasoning_effort`, así que volver atrás por env tiene que quitarlo.
"""
from __future__ import annotations

import pytest

from app.services.openai_chat import DEFAULT_REASONING_TOKEN_MARGIN, openai_chat_kwargs

_ENV_VARS = (
    "OPENAI_CHAT_MODEL",
    "OPENAI_FAST_MODEL",
    "OPENAI_CHAT_EFFORT",
    "OPENAI_FAST_EFFORT",
    "OPENAI_REASONING_TOKEN_MARGIN",
)


@pytest.fixture(autouse=True)
def _clean_openai_env(monkeypatch):
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_por_defecto_luna_sin_razonamiento_y_con_temperature():
    kwargs = openai_chat_kwargs("chat", temperature=0.7, max_completion_tokens=2000)

    assert kwargs == {
        "model": "gpt-6-luna",
        "reasoning_effort": "none",
        "max_completion_tokens": 2000,
        "temperature": 0.7,
    }
    assert "max_tokens" not in kwargs


def test_el_effort_va_siempre_explicito_aunque_no_haya_temperature():
    # Sin effort explícito Luna usaría medium; ninguna llamada puede depender de eso.
    kwargs = openai_chat_kwargs("fast")

    assert kwargs == {"model": "gpt-6-luna", "reasoning_effort": "none"}


def test_effort_low_quita_temperature_y_top_p_y_suma_margen(monkeypatch):
    monkeypatch.setenv("OPENAI_CHAT_EFFORT", "low")
    kwargs = openai_chat_kwargs("chat", temperature=0.7, top_p=0.9, max_completion_tokens=2000)

    assert kwargs == {
        "model": "gpt-6-luna",
        "reasoning_effort": "low",
        "max_completion_tokens": 2000 + DEFAULT_REASONING_TOKEN_MARGIN,
    }


def test_el_margen_de_razonamiento_es_configurable(monkeypatch):
    monkeypatch.setenv("OPENAI_FAST_EFFORT", "medium")
    monkeypatch.setenv("OPENAI_REASONING_TOKEN_MARGIN", "500")

    kwargs = openai_chat_kwargs("fast", max_completion_tokens=200)

    assert kwargs["max_completion_tokens"] == 700


def test_volver_a_gpt4o_por_env_no_manda_reasoning_effort(monkeypatch):
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_CHAT_EFFORT", "low")  # se ignora: gpt-4o no razona

    kwargs = openai_chat_kwargs("chat", temperature=0.3, max_completion_tokens=120)

    assert kwargs == {"model": "gpt-4o", "max_completion_tokens": 120, "temperature": 0.3}


def test_los_niveles_son_independientes(monkeypatch):
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "gpt-4o")

    assert openai_chat_kwargs("chat")["model"] == "gpt-4o"
    assert openai_chat_kwargs("fast")["model"] == "gpt-6-luna"


def test_variables_vacias_del_compose_equivalen_a_no_fijarlas(monkeypatch):
    # docker-compose pasa `${OPENAI_CHAT_MODEL:-}`: llega una cadena vacía, no None.
    for var in _ENV_VARS:
        monkeypatch.setenv(var, "")

    kwargs = openai_chat_kwargs("chat", temperature=0.2, max_completion_tokens=300)

    assert kwargs == {
        "model": "gpt-6-luna",
        "reasoning_effort": "none",
        "max_completion_tokens": 300,
        "temperature": 0.2,
    }


def test_generated_by_lee_el_modelo_al_insertar_no_al_importar(monkeypatch):
    from app.db.models import SeoContent

    default = SeoContent.__table__.c.generated_by.default
    assert default.is_callable

    monkeypatch.setenv("OPENAI_CHAT_MODEL", "gpt-4o")
    assert default.arg(None) == "gpt-4o"
    monkeypatch.delenv("OPENAI_CHAT_MODEL")
    assert default.arg(None) == "gpt-6-luna"
