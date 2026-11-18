#!/usr/bin/env python3
"""Cada predicado de `data/relaciones.yaml`, y su inversa, tiene etiqueta en la web.

Las relaciones verificadas se PINTAN en la ficha desde el mismo fragmento JSON-LD que
se marca (`web/lib/relaciones-jsonld.ts`, `ETIQUETAS_RELACION`). Un predicado sin
etiqueta saldría en la ficha con su nombre en inglés («foundingLocation»). Las
inversas las deriva `api/app/services/relations.py` (`INVERSA`) al servir.

No puede ir en pytest: la imagen del api no ve `web/`. Corre en el runner del CI.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
yaml_txt = (RAIZ / "data/relaciones.yaml").read_text(encoding="utf-8")
predicados = {p for p in re.findall(r"^\s+predicado:\s*(\w+)", yaml_txt, re.MULTILINE) if p != "sameAs"}

rel_txt = (RAIZ / "api/app/services/relations.py").read_text(encoding="utf-8")
bloque = re.search(r"INVERSA\s*=\s*\{(.*?)\}", rel_txt, re.DOTALL)
inversa = dict(re.findall(r'"(\w+)":\s*"(\w+)"', bloque.group(1))) if bloque else {}

ts = (RAIZ / "web/lib/relaciones-jsonld.ts").read_text(encoding="utf-8")
bloque_ts = re.search(r"ETIQUETAS_RELACION[^=]*=\s*\{(.*?)\};", ts, re.DOTALL)
etiquetas = set(re.findall(r"^\s*(\w+):", bloque_ts.group(1), re.MULTILINE)) if bloque_ts else set()

necesarios = predicados | {inversa[p] for p in predicados if p in inversa}
faltan = sorted(necesarios - etiquetas)
print(f"{len(predicados)} predicados en el YAML · {len(necesarios)} con inversas · "
      f"{len(etiquetas)} etiquetas en la web")
if faltan:
    print("::error::sin etiqueta en web/lib/relaciones-jsonld.ts:", ", ".join(faltan))
    sys.exit(1)
