"""Carga el manual de estilo de habla de Robe (data/robe_speech_style.md) para
inyectarlo en el prompt del consultorio. Destilado de sus entrevistas reales por
scripts.research.analyze_robe_style. Cacheado."""
from __future__ import annotations

import os
from functools import lru_cache


def _path() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (
        "/app/data/robe_speech_style.md",
        os.path.normpath(os.path.join(here, "..", "..", "..", "data", "robe_speech_style.md")),
        os.path.normpath(os.path.join(here, "..", "..", "data", "robe_speech_style.md")),
    ):
        if os.path.exists(p):
            return p
    return None


@lru_cache(maxsize=1)
def speech_style() -> str | None:
    p = _path()
    if not p:
        return None
    txt = open(p, encoding="utf-8").read().strip()
    return txt or None
