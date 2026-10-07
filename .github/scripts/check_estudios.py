#!/usr/bin/env python3
"""Comprueba que el registro de estudios del frontend y el del backend coinciden.

Los estudios se declaran DOS veces: `web/lib/estudios.ts` (metadatos, resumen, el
componente que lo pinta) y `api/app/services/estudios.py` (lo que necesitan la
guarda de enlaces internos y la newsletter). No se puede unificar: la imagen del
api se construye con contexto `./api` y la del web con `./web`, así que ninguna ve
la otra ni `data/` del raíz.

Si divergen pasan dos cosas, las dos en silencio: `guard_internal_links` da el
enlace al estudio por inventado y lo desenlaza al republicar el post, y la
newsletter deja de anunciarlo. Se comparan slug, título y fecha, porque el título
y la fecha son lo que imprime el correo.

Corre en el runner del CI, donde está el repo entero.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
TS = RAIZ / "web" / "lib" / "estudios.ts"
PY_ = RAIZ / "api" / "app" / "services" / "estudios.py"


def _campo(bloque: str, nombre: str, patron: str) -> str | None:
    m = re.search(patron, bloque)
    return m.group(1) if m else None


def registro_ts() -> dict[str, tuple[str, str]]:
    texto = TS.read_text(encoding="utf-8")
    cuerpo = texto.split("export const ESTUDIOS", 1)[1].split("export const estudioPorSlug", 1)[0]
    salida: dict[str, tuple[str, str]] = {}
    # Una entrada por `slug:`; el bloque va de ese slug al siguiente.
    trozos = re.split(r'(?=slug:\s*")', cuerpo)
    for trozo in trozos:
        slug = _campo(trozo, "slug", r'slug:\s*"([^"]+)"')
        if slug is None:
            continue
        titulo = _campo(trozo, "titulo", r'titulo:\s*\n?\s*"((?:[^"\\]|\\.)*)"')
        fecha = _campo(trozo, "datePublished", r'datePublished:\s*"(\d{4}-\d{2}-\d{2})"')
        salida[slug] = (titulo or "", fecha or "")
    return salida


def registro_py() -> dict[str, tuple[str, str]]:
    texto = PY_.read_text(encoding="utf-8")
    cuerpo = texto.split("ESTUDIOS: tuple[Estudio, ...]", 1)[1].split("ESTUDIO_SLUGS", 1)[0]
    salida: dict[str, tuple[str, str]] = {}
    for trozo in re.split(r'(?=slug=")', cuerpo):
        slug = _campo(trozo, "slug", r'slug="([^"]+)"')
        if slug is None:
            continue
        titulo = _campo(trozo, "titulo", r'titulo=\s*\n?\s*"((?:[^"\\]|\\.)*)"')
        m = re.search(r"publicado=date\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\)", trozo)
        fecha = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""
        salida[slug] = (titulo or "", fecha)
    return salida


def main() -> int:
    for f in (TS, PY_):
        if not f.is_file():
            sys.exit(f"no encuentro {f}")
    ts, py = registro_ts(), registro_py()
    if not ts:
        sys.exit(f"{TS} no declara ningún estudio: ¿ha cambiado la forma del registro?")
    if not py:
        sys.exit(f"{PY_} no declara ningún estudio: ¿ha cambiado la forma del registro?")

    fallos: list[str] = []
    for slug in sorted(set(ts) | set(py)):
        if slug not in py:
            fallos.append(f"  · «{slug}» está en el frontend y NO en el backend")
            continue
        if slug not in ts:
            fallos.append(f"  · «{slug}» está en el backend y NO en el frontend")
            continue
        t_tit, t_fec = ts[slug]
        p_tit, p_fec = py[slug]
        if t_tit != p_tit:
            fallos.append(f"  · «{slug}» título distinto:\n      web: {t_tit!r}\n      api: {p_tit!r}")
        if t_fec != p_fec:
            fallos.append(f"  · «{slug}» fecha distinta: web {t_fec} · api {p_fec}")

    if fallos:
        print("los registros de estudios divergen:")
        print("\n".join(fallos))
        sys.exit(
            "\nArréglalo en las DOS listas (web/lib/estudios.ts y "
            "api/app/services/estudios.py). Si no, el enlace interno al estudio se "
            "desenlaza solo y la newsletter deja de anunciarlo."
        )
    print(f"{len(ts)} estudio(s) sincronizado(s): {', '.join(sorted(ts))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
