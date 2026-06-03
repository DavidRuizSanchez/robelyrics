"""Loader de citas verificadas de Robe (data/robe_quotes.yaml) para usar desde
la app (consultorio). Espejo ligero del loader de scripts/seo/common.py, pero
importable desde los routers sin arrastrar el módulo de scripts.

Solo devuelve citas `verified: true`. `tone_quotes(tags, k)` prioriza las que
comparten tags con la pregunta y rellena con el resto (orden estable, sin azar
para no romper caché de prompt)."""
from __future__ import annotations

import os
from functools import lru_cache

import yaml


def _yaml_path() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (
        "/app/data/robe_quotes.yaml",
        os.path.normpath(os.path.join(here, "..", "..", "..", "data", "robe_quotes.yaml")),
        os.path.normpath(os.path.join(here, "..", "..", "data", "robe_quotes.yaml")),
    ):
        if os.path.exists(p):
            return p
    return None


@lru_cache(maxsize=1)
def _all_quotes() -> tuple[dict, ...]:
    path = _yaml_path()
    if not path:
        return ()
    data = yaml.safe_load(open(path, encoding="utf-8")) or {}
    out = []
    for q in data.get("quotes") or []:
        if q.get("verified") and (q.get("text") or "").strip():
            out.append({"text": q["text"].strip(), "tags": set(q.get("tags") or [])})
    return tuple(out)


def tone_quotes(tags: list[str] | None = None, k: int = 4) -> list[str]:
    """Devuelve hasta k citas verificadas, priorizando las que comparten `tags`."""
    quotes = _all_quotes()
    if not quotes:
        return []
    wanted = {t.lower() for t in (tags or [])}
    scored = sorted(
        quotes,
        key=lambda q: -len(wanted & {t.lower() for t in q["tags"]}),
    )
    return [q["text"] for q in scored[:k]]
