"""Analítica de uso de features para el admin (F2.4).

Cuánto se usan las features (consultorio, buscador, completar, mood) y QUÉ consulta
la gente. El ratio agregado también va a GA4 (eventos en el front); esto da el detalle
con el texto de las consultas, que no debe ir a analytics por PII.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ConsultQuestion, FeatureQuery, User
from app.db.session import get_db
from app.services.auth import get_current_admin

router = APIRouter(prefix="/admin/usage", tags=["analytics"])


class FeatureCount(BaseModel):
    feature: str
    total: int


class UsageSummary(BaseModel):
    days: int
    by_feature: list[FeatureCount]
    consultorio_total: int
    consultorio_sin_respuesta: int  # grounded=false: huecos de conocimiento


class TopQuery(BaseModel):
    query: str
    veces: int


def _since(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


@router.get("/summary", response_model=UsageSummary)
def usage_summary(
    days: int = 30,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> UsageSummary:
    since = _since(days)
    rows = db.execute(
        select(FeatureQuery.feature, func.count())
        .where(FeatureQuery.created_at >= since)
        .group_by(FeatureQuery.feature)
    ).all()
    by_feature = [FeatureCount(feature=f, total=int(n)) for f, n in rows]

    c_total = db.execute(
        select(func.count()).select_from(ConsultQuestion).where(ConsultQuestion.created_at >= since)
    ).scalar_one()
    c_nores = db.execute(
        select(func.count()).select_from(ConsultQuestion).where(
            ConsultQuestion.created_at >= since,
            ConsultQuestion.grounded.is_(False),
        )
    ).scalar_one()
    by_feature.append(FeatureCount(feature="consultorio", total=int(c_total)))
    return UsageSummary(
        days=days, by_feature=sorted(by_feature, key=lambda x: -x.total),
        consultorio_total=int(c_total), consultorio_sin_respuesta=int(c_nores),
    )


@router.get("/top", response_model=list[TopQuery])
def top_queries(
    feature: str,
    days: int = 30,
    limit: int = 20,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
) -> list[TopQuery]:
    """Consultas más frecuentes de una feature. `feature=consultorio` mira la tabla
    del consultorio; el resto, feature_queries."""
    since = _since(days)
    if feature == "consultorio":
        col, model = ConsultQuestion.question, ConsultQuestion
    else:
        col, model = FeatureQuery.query, FeatureQuery
    q = (
        select(func.lower(col).label("q"), func.count().label("n"))
        .where(model.created_at >= since)
    )
    if model is FeatureQuery:
        q = q.where(FeatureQuery.feature == feature)
    q = q.group_by(func.lower(col)).order_by(func.count().desc()).limit(limit)
    return [TopQuery(query=r.q, veces=int(r.n)) for r in db.execute(q).all()]
