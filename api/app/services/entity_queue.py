"""Cola del panel «Relaciones y entidades» (plan de relaciones, 18-11-2026).

Dos cosas esperan una decisión humana:

- **Relaciones pendientes** (`entity_relations.status = 'pendiente'`): las que no llegan a
  un T1 o a dos T2 (un concierto que solo recoge un archivo de aficionados, por ejemplo).
  Aprobar las da por verificadas con quien decide; rechazar las deja fuera para siempre.
- **Entidades propuestas** (`entity_proposals`): la otra punta de una relación verificada
  que no tiene página. Aprobar significa «hazle ficha»; no la publica: la ficha sigue el
  circuito de siempre (borrador, revisión, publicación).
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

ESTADOS_PROPUESTA = ("propuesta", "aprobada", "publicada", "descartada")
_ACCIONES_PROPUESTA = {
    "aprobar": (("propuesta", "descartada"), "aprobada"),
    "descartar": (("propuesta", "aprobada"), "descartada"),
    "recuperar": (("descartada",), "propuesta"),
}
_ACCIONES_RELACION = {
    "aprobar": (("pendiente",), "verificada"),
    "rechazar": (("pendiente",), "rechazada"),
}


class AccionNoValida(ValueError):
    pass


def _ref_texto(db: Session, tipo: str, ident: int) -> tuple[str, str | None]:
    from app.services.relations import ref_por_id

    ref = ref_por_id(db, tipo, ident)
    if ref is None:
        return f"{tipo}:{ident}", None
    return ref.nombre, ref.path


def listar(db: Session, *, limite: int = 200) -> dict:
    from app.db.models import EntityProposal, EntityRelation

    cuenta: dict[str, int] = {}
    filas: dict[str, list[dict]] = {}
    for estado in ESTADOS_PROPUESTA:
        q = db.query(EntityProposal).filter(EntityProposal.estado == estado)
        cuenta[estado] = q.count()
        filas[estado] = [{
            "id": p.id, "tipo": p.tipo, "nombre": p.nombre, "qid": p.qid,
            "relaciones": p.relaciones or [], "material": p.material, "demanda": p.demanda,
            "estado": p.estado, "nota": p.nota,
        } for p in q.order_by(EntityProposal.material.desc().nullslast(),
                              EntityProposal.nombre).limit(limite).all()]

    q = db.query(EntityRelation).filter(EntityRelation.status == "pendiente")
    pendientes = []
    for r in q.order_by(EntityRelation.subject_type, EntityRelation.id).limit(limite).all():
        suj, suj_path = _ref_texto(db, r.subject_type, r.subject_id)
        if r.object_id is not None:
            obj, obj_path = _ref_texto(db, r.object_type, r.object_id)
        else:
            lit = r.object_literal or {}
            obj, obj_path = (lit.get("name") if isinstance(lit, dict) else str(lit)), None
        pendientes.append({
            "id": r.id, "sujeto": suj, "sujeto_path": suj_path, "predicado": r.predicate,
            "objeto": obj, "objeto_path": obj_path, "rol": r.role_name,
            "fuentes": r.fuentes or [],
        })
    return {"cuenta": cuenta, "propuestas": filas,
            "relaciones_pendientes": pendientes, "n_relaciones_pendientes": q.count()}


def decidir_propuesta(db: Session, ident: int, accion: str, *, quien: str = "david") -> dict:
    from app.db.models import EntityProposal

    p = db.get(EntityProposal, ident)
    if p is None:
        raise LookupError(ident)
    desde, hacia = _ACCIONES_PROPUESTA.get(accion, ((), None))
    if p.estado not in desde:
        raise AccionNoValida(f"«{accion}» no vale desde «{p.estado}»")
    p.estado = hacia
    p.decidida_por = quien
    p.decidida_at = p.updated_at = datetime.now(UTC)
    db.commit()
    return {"id": p.id, "estado": p.estado}


def decidir_relacion(db: Session, ident: int, accion: str, *, quien: str = "david") -> dict:
    from app.db.models import EntityRelation

    r = db.get(EntityRelation, ident)
    if r is None:
        raise LookupError(ident)
    desde, hacia = _ACCIONES_RELACION.get(accion, ((), None))
    if r.status not in desde:
        raise AccionNoValida(f"«{accion}» no vale desde «{r.status}»")
    r.status = hacia
    ahora = datetime.now(UTC)
    if hacia == "verificada":
        r.verified_by = quien
        r.verified_at = ahora
    r.updated_at = ahora
    db.commit()
    return {"id": r.id, "status": r.status}
