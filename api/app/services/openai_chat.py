"""Modelo y parámetros comunes de todas las llamadas a Chat Completions de OpenAI.

OpenAI apaga gpt-4o, gpt-4o-mini, gpt-4.1 y gpt-4.1-mini el 14-01-2027 y su
sustituto es `gpt-6-luna`. Luna razona y eso cambia qué parámetros acepta
(comprobado contra la API el 19-10-2026):

- Sin `reasoning_effort` usa `medium` y entonces rechaza `temperature` con un 400.
- Con `reasoning_effort="none"` acepta `temperature` y `top_p`, como un GPT-4.x.
- Con cualquier otro effort hay que quitar `temperature`, `top_p` y `logprobs`.
- `max_tokens` da un 400: va `max_completion_tokens`, que incluye los tokens
  de razonamiento.
- gpt-4o, en cambio, rechaza `reasoning_effort`.

Por eso ninguna llamada pasa estos parámetros a mano: los arma
`openai_chat_kwargs` según el modelo que toque. Así se puede volver a gpt-4o
(`OPENAI_CHAT_MODEL=gpt-4o`) o subir el razonamiento (`OPENAI_CHAT_EFFORT=low`)
desde el entorno, sin tocar código.

Hay dos niveles: `chat` (antes gpt-4o: generación, revisión, visión) y `fast`
(antes gpt-4o-mini: clasificadores y jueces baratos). El entorno se lee en cada
llamada, no al importar.
"""
from __future__ import annotations

import os
from typing import Any, Literal

ModelTier = Literal["chat", "fast"]

DEFAULT_MODEL = "gpt-6-luna"
DEFAULT_EFFORT = "none"
# Colchón que se suma a `max_completion_tokens` cuando hay razonamiento: los
# topes de cada llamada se pensaron para la salida visible y, sin él, el
# razonamiento se comería la respuesta.
DEFAULT_REASONING_TOKEN_MARGIN = 2000

# Familias que aceptan `reasoning_effort`. Las GPT-4.x lo rechazan con un 400.
_REASONING_MODEL_PREFIXES = ("gpt-5", "gpt-6", "o1", "o3", "o4")

_MODEL_ENV = {"chat": "OPENAI_CHAT_MODEL", "fast": "OPENAI_FAST_MODEL"}
_EFFORT_ENV = {"chat": "OPENAI_CHAT_EFFORT", "fast": "OPENAI_FAST_EFFORT"}


def model_for(tier: ModelTier) -> str:
    return os.environ.get(_MODEL_ENV[tier], "").strip() or DEFAULT_MODEL


def effort_for(tier: ModelTier) -> str:
    return os.environ.get(_EFFORT_ENV[tier], "").strip() or DEFAULT_EFFORT


def is_reasoning_model(model: str) -> bool:
    return model.startswith(_REASONING_MODEL_PREFIXES)


def _reasoning_token_margin() -> int:
    raw_margin = os.environ.get("OPENAI_REASONING_TOKEN_MARGIN", "").strip()
    return int(raw_margin) if raw_margin else DEFAULT_REASONING_TOKEN_MARGIN


def openai_chat_kwargs(
    tier: ModelTier,
    *,
    max_completion_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> dict[str, Any]:
    """`model` y parámetros de muestreo para `client.chat.completions.create(**...)`."""
    model = model_for(tier)
    kwargs: dict[str, Any] = {"model": model}
    sampling_allowed = True

    if is_reasoning_model(model):
        effort = effort_for(tier)
        kwargs["reasoning_effort"] = effort
        if effort != "none":
            sampling_allowed = False
            if max_completion_tokens is not None:
                max_completion_tokens += _reasoning_token_margin()

    if max_completion_tokens is not None:
        kwargs["max_completion_tokens"] = max_completion_tokens
    if sampling_allowed:
        if temperature is not None:
            kwargs["temperature"] = temperature
        if top_p is not None:
            kwargs["top_p"] = top_p
    return kwargs
