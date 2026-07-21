"""Circuito de erratas de fans + gestión admin + feed de auditoría.

Filosofía del vuelco: un fan de confianza reporta una errata (letra mal, autoría,
disco/año, interpretación) y NO va directa al humano: queda `pending` y el Motor de
Consenso (run_consensus_sweep) intenta resolverla sola; solo el residuo ambiguo
llega a la cola admin. Además, toda auto-corrección del MCV queda en un feed de
auditoría (VerificationRecord) que el admin puede revisar y revertir.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ErrataReport, User, VerificationRecord
from app.db.session import get_db
from app.services.auth import get_current_admin, get_current_user

router = APIRouter(prefix="/errata", tags=["errata"])

_TARGETS = {"song_lyrics", "authorship", "catalog", "interpretation"}


class ErrataIn(BaseModel):
    target_type: str = Field(..., description="song_lyrics|authorship|catalog|interpretation")
    target_id: int | None = None
    field: str | None = None
    reported_wrong: str | None = None
    suggested_right: str | None = None
    note: str | None = None


class ErrataOut(BaseModel):
    id: int
    status: str
    message: str


@router.post("", response_model=ErrataOut)
def report_errata(
    payload: ErrataIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ErrataOut:
    """Un fan reporta una errata. Queda `pending`; el MCV la intentará resolver."""
    if payload.target_type not in _TARGETS:
        raise HTTPException(status_code=422, detail="target_type no válido")
    if not (payload.reported_wrong or payload.suggested_right or payload.note):
        raise HTTPException(status_code=422, detail="di qué está mal o qué debería decir")
    rep = ErrataReport(
        target_type=payload.target_type,
        target_id=payload.target_id,
        field=(payload.field or None),
        reported_wrong=(payload.reported_wrong or None),
        suggested_right=(payload.suggested_right or None),
        reporter=user.email,
        note=(payload.note or None),
        status="pending",
    )
    db.add(rep)
    db.commit()
    db.refresh(rep)
    return ErrataOut(
        id=rep.id, status=rep.status,
        message="Gracias por el aviso. Lo contrastamos con nuestras fuentes y, si toca, se corrige.",
    )


# --------------------------------------------------------------------------- #
# Admin: cola de erratas + feed de auditoría
# --------------------------------------------------------------------------- #
class ErrataAdminItem(BaseModel):
    id: int
    target_type: str
    target_id: int | None
    field: str | None
    reported_wrong: str | None
    suggested_right: str | None
    reporter: str | None
    note: str | None
    status: str
    resolution_note: str | None
    created_at: datetime


@router.get("/admin", response_model=list[ErrataAdminItem])
def admin_list(
    status: str | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[ErrataAdminItem]:
    """Cola de erratas. Por defecto las que requieren humano (needs_human + pending)."""
    q = select(ErrataReport).order_by(ErrataReport.created_at.desc())
    if status:
        q = q.where(ErrataReport.status == status)
    else:
        q = q.where(ErrataReport.status.in_(("needs_human", "pending")))
    return [ErrataAdminItem.model_validate(r, from_attributes=True) for r in db.execute(q).scalars().all()]


class ResolveIn(BaseModel):
    action: str = Field(..., description="applied|rejected")
    note: str | None = None


@router.post("/admin/{errata_id}/resolve", response_model=ErrataOut)
def admin_resolve(
    errata_id: int,
    payload: ResolveIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> ErrataOut:
    """El admin marca una errata como aplicada (tras corregir) o rechazada."""
    if payload.action not in ("applied", "rejected"):
        raise HTTPException(status_code=422, detail="action debe ser applied|rejected")
    rep = db.get(ErrataReport, errata_id)
    if not rep:
        raise HTTPException(status_code=404, detail="errata no encontrada")
    rep.status = payload.action
    rep.resolution_note = payload.note
    rep.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return ErrataOut(id=rep.id, status=rep.status, message="Errata actualizada.")


class AuditItem(BaseModel):
    id: int
    claim_kind: str
    claim_key: str
    song_id: int | None
    old_value: str | None
    new_value: str | None
    verdict: str
    confidence: float
    auto_applied: bool
    reverted: bool
    checked_at: datetime


@router.get("/admin/audit", response_model=list[AuditItem])
def admin_audit(
    only_applied: bool = True,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[AuditItem]:
    """Feed de auditoría: auto-correcciones del MCV (trust-but-verify)."""
    q = select(VerificationRecord).order_by(VerificationRecord.checked_at.desc())
    if only_applied:
        q = q.where(VerificationRecord.auto_applied.is_(True))
    return [AuditItem.model_validate(r, from_attributes=True) for r in db.execute(q.limit(200)).scalars().all()]
