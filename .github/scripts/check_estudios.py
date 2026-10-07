#!/usr/bin/env python3
"""Comprueba que el registro de estudios del frontend y los slugs del backend coinciden.

Corre en el runner del CI, no dentro del contenedor del api: la imagen se
construye solo con `api/` y no ve `web/`, así que un test de pytest no puede leer
el registro TS. Sin esta comprobación, añadir un estudio al frontend y olvidarse
del backend hace que `guard_internal_links` dé el enlace por inventado y lo
desenlace en silencio al republicar el post.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
TS = RAIZ / "web" / "lib" / "estudios.ts"
PY_ = RAIZ / "api" / "app" / "services" / "url_resolver.py"


def slugs_ts() -> set[str]:
    texto = TS.read_text(encoding="utf-8")
    cuerpo = texto.split("export const ESTUDIOS", 1)[1].split("export const estudioPorSlug", 1)[0]
    return set(re.findall(r'slug:\s*"([^"]+)"', cuerpo))


def slugs_py() -> set[str]:
    texto = PY_.read_text(encoding="utf-8")
    bloque = re.search(r"ESTUDIO_SLUGS:\s*frozenset\[str\]\s*=\s*frozenset\(\{(.*?)\}\)", texto, re.S)
    if bloque is None:
        sys.exit(f"no encuentro ESTUDIO_SLUGS en {PY_}")
    return set(re.findall(r'"([^"]+)"', bloque.group(1)))


def main() -> int:
    for f in (TS, PY_):
        if not f.is_file():
            sys.exit(f"no encuentro {f}")
    ts, py = slugs_ts(), slugs_py()
    if not ts:
        sys.exit(f"{TS} no declara ningún estudio: ¿ha cambiado la forma del registro?")
    if ts != py:
        print(f"solo en web/lib/estudios.ts: {sorted(ts - py) or '—'}")
        print(f"solo en url_resolver.ESTUDIO_SLUGS: {sorted(py - ts) or '—'}")
        sys.exit(
            "los estudios divergen. Añade el slug a las DOS listas, o el enlace "
            "interno al estudio se desenlazará solo."
        )
    print(f"{len(ts)} estudio(s) sincronizado(s): {', '.join(sorted(ts))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
