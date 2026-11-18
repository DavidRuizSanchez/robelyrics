"""Carga en `entity_proposals` las entidades sin página que salen de las relaciones.

Plan de relaciones (18-11-2026), PR D. Fuentes:
- el CSV de propuestas de `scripts.relaciones.descubrir` (qid, nombre, tipo, relaciones);
- el CSV de ciudades sin ficha de `scripts.relaciones.conciertos`.

Para cada una mide dos cosas, sin inventar nada:
- **material**: cuántas fuentes del corpus la nombran (con qué escribir su ficha);
- **demanda**: su volumen de búsqueda en España (DataForSEO `search_volume`), con fecha.

Idempotente por `clave` (`qid:Q…`, o `ciudad:<nombre>`): no pisa lo que ya se decidió.

    python -m scripts.relaciones.propuestas --descubrir /tmp/rel/propuestas_entidades.csv \\
        --ciudades /tmp/conc/ciudades_sin_ficha.csv [--sin-demanda]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from datetime import UTC, datetime

from sqlalchemy import text

from app.db.models import EntityProposal
from app.db.session import SessionLocal


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


def material(db, nombre: str) -> int:
    """Fuentes del corpus que nombran a la entidad como palabra completa."""
    if len(nombre) < 4:
        return 0
    patron = r"\m" + re.escape(nombre) + r"\M"
    return db.execute(text("select count(*) from interpretation_sources where content_clean ~* :p"),
                      {"p": patron}).scalar() or 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--descubrir")
    ap.add_argument("--ciudades")
    ap.add_argument("--sin-demanda", action="store_true")
    args = ap.parse_args()

    entradas: dict[str, dict] = {}
    if args.descubrir:
        with open(args.descubrir, encoding="utf-8") as fh:
            filas_descubrir = list(csv.DictReader(fh))
        for f in filas_descubrir:
            rels = [{"desde": r.split(" ")[0], "predicado": r.split(" ")[1] if " " in r else ""}
                    for r in (f.get("relaciones") or "").split(" | ") if r.strip()]
            entradas[f"qid:{f['qid']}"] = {"tipo": f["tipo"], "nombre": f["nombre"],
                                            "qid": f["qid"], "relaciones": rels}
    if args.ciudades:
        with open(args.ciudades, encoding="utf-8") as fh:
            filas_ciudades = list(csv.DictReader(fh))
        for f in filas_ciudades:
            clave = f"ciudad:{_norm(f['ciudad'])}"
            conciertos = [c for c in (f.get("conciertos") or "").split(" | ") if c.strip()]
            e = entradas.setdefault(clave, {"tipo": "Place", "nombre": f["ciudad"], "qid": None,
                                            "relaciones": []})
            e["relaciones"] += [{"desde": "conciertos.csv", "predicado": "event",
                                 "detalle": c} for c in conciertos]

    db = SessionLocal()
    volumenes: dict[str, int] = {}
    if not args.sin_demanda and entradas:
        from app.services.seo_research import search_volume

        nombres = sorted({e["nombre"] for e in entradas.values()})
        for i in range(0, len(nombres), 700):
            for k, v in search_volume(nombres[i:i + 700]).items():
                volumenes[k] = v.volume
    hoy = datetime.now(UTC).strftime("%Y-%m-%d")
    nuevas = actualizadas = 0
    for clave, e in entradas.items():
        fila = db.query(EntityProposal).filter(EntityProposal.clave == clave).first()
        demanda = ({"volumen": volumenes.get(e["nombre"].lower(), 0), "fuente": "DataForSEO "
                    "search_volume (ES)", "fecha": hoy} if volumenes else None)
        if fila is None:
            db.add(EntityProposal(clave=clave, tipo=e["tipo"], nombre=e["nombre"], qid=e["qid"],
                                  relaciones=e["relaciones"], material=material(db, e["nombre"]),
                                  demanda=demanda))
            nuevas += 1
        else:
            fila.relaciones = e["relaciones"]
            fila.material = material(db, e["nombre"])
            if demanda:
                fila.demanda = demanda
            fila.updated_at = datetime.now(UTC)
            actualizadas += 1
    db.commit()
    print(json.dumps({"nuevas": nuevas, "actualizadas": actualizadas,
                      "con_demanda": sum(1 for v in volumenes.values() if v)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
