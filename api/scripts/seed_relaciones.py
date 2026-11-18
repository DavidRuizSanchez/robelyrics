"""Carga `data/relaciones.yaml` en `entity_relations`, validando cada una.

    python -m scripts.seed_relaciones --dry-run     # valida y cuenta, no escribe
    python -m scripts.seed_relaciones               # escribe

Idempotente: la clave de cada relación es derivada (`relations.clave`), así que
repetir la carga no duplica. **Nunca pisa una relación `verificada`** con algo que no
lo sea: si el YAML trae una versión distinta, se avisa y se deja la de la BD.

Sale con 1 si alguna relación no pasa la validación (y no escribe ninguna: o todo o
nada, para que un YAML a medias no deje la tabla a medias).
"""
from __future__ import annotations

import argparse
import contextlib
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app.db.models import EntityRelation
from app.db.session import SessionLocal
from app.services import relations
from app.services.jsonld_audit import ruta_data


def cargar_propuestas(ruta: Path) -> list[relations.Propuesta]:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    out = []
    for i, r in enumerate(datos.get("relaciones") or []):
        try:
            out.append(relations.Propuesta(
                sujeto=r["sujeto"], predicado=r["predicado"], objeto=r["objeto"],
                rol=r.get("rol"), desde=_texto(r.get("desde")), hasta=_texto(r.get("hasta")),
                estado=r.get("estado", "pendiente"), verificado_por=r.get("verificado_por"),
                fuentes=r.get("fuentes") or []))
        except KeyError as exc:
            raise SystemExit(f"relación #{i}: falta {exc}") from exc
    return out


def _texto(v) -> str | None:
    return None if v is None else str(v)


def aplicar(db, filas: list[dict]) -> dict[str, int]:
    cuenta = {"nuevas": 0, "actualizadas": 0, "iguales": 0, "protegidas": 0}
    ahora = datetime.now(UTC)
    for fila in filas:
        previa = db.query(EntityRelation).filter(EntityRelation.clave == fila["clave"]).first()
        if previa is None:
            db.add(EntityRelation(**fila, verified_at=ahora if fila["status"] == "verificada"
                                  else None))
            cuenta["nuevas"] += 1
            continue
        cambios = {k: v for k, v in fila.items() if getattr(previa, k) != v}
        if not cambios:
            cuenta["iguales"] += 1
            continue
        if previa.status == "verificada" and fila["status"] != "verificada":
            print(f"  PROTEGIDA (ya verificada en la BD, no se pisa): {fila['clave']}")
            cuenta["protegidas"] += 1
            continue
        for k, v in cambios.items():
            setattr(previa, k, v)
        if fila["status"] == "verificada" and "status" in cambios:
            previa.verified_at = ahora
        previa.updated_at = ahora
        cuenta["actualizadas"] += 1
    return cuenta


def cargar(db, propuestas: list[relations.Propuesta]) -> tuple[dict[str, int], list[str]]:
    """Valida y aplica en DOS pasadas, sin commit: primero las identidades (`sameAs`) y
    luego el resto. Una relación que cita MusicBrainz exige la identidad acreditada de
    sujeto y objeto, y esa identidad puede venir en el mismo fichero: validándolo todo
    de una vez, se rechazaría. Si algo falla, no se aplica nada (lo deshace quien llama).
    """
    total = {"nuevas": 0, "actualizadas": 0, "iguales": 0, "protegidas": 0}
    rechazadas: list[str] = []
    claves: list[str] = []
    for grupo in ([p for p in propuestas if p.predicado == "sameAs"],
                  [p for p in propuestas if p.predicado != "sameAs"]):
        filas = []
        for p in grupo:
            errores, fila = relations.validar(db, p)
            if errores:
                rechazadas.append(f"{p.sujeto} {p.predicado} {p.objeto}: {'; '.join(errores)}")
            else:
                filas.append(fila)
                claves.append(fila["clave"])
        if rechazadas:
            return total, rechazadas
        if len(set(claves)) != len(claves):
            return total, ["hay relaciones repetidas en el YAML (misma clave)"]
        for k, v in aplicar(db, filas).items():
            total[k] += v
        db.flush()   # la segunda pasada tiene que ver las identidades de la primera
    return total, rechazadas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    # Por defecto, las dos fuentes: la curada a mano y la descubierta por
    # `scripts.relaciones` (18-11-2026). Se validan juntas: las identidades de una
    # pueden hacer falta para las relaciones de la otra.
    ap.add_argument("--yaml", action="append",
                    help="YAML a cargar (repetible). Por defecto: relaciones.yaml y "
                         "relaciones_auto.yaml")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rutas = args.yaml or [str(ruta_data("relaciones.yaml"))]
    if not args.yaml:
        with contextlib.suppress(FileNotFoundError):
            rutas.append(str(ruta_data("relaciones_auto.yaml")))
    propuestas = [p for ruta in rutas for p in cargar_propuestas(Path(ruta))]
    db = SessionLocal()
    try:
        cuenta, rechazadas = cargar(db, propuestas)
        for r in rechazadas:
            print(f"  RECHAZADA {r}")
        print(f"{len(propuestas)} relaciones en el YAML · {len(rechazadas)} rechazadas")
        if rechazadas:
            db.rollback()
            sys.exit(1)
        print(cuenta)
        if args.dry_run:
            db.rollback()
            print("dry-run: nada escrito")
        else:
            db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
