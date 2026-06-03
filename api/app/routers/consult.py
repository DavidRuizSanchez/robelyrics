"""Consultorio "Pregúntale al viento": endpoint privado de Q&A en la voz de Robe.

Solo para usuarios autenticados (gancho de captación: hay que registrarse).
Rate-limit por IP + moderación + logging en consult_questions.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import ConsultQuestion, User
from app.db.session import get_db
from app.services import consult as consult_svc
from app.services.auth import get_current_user
from app.services.rate_limit import limiter

router = APIRouter(prefix="/consult", tags=["consult"])


class ConsultAskIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class Citation(BaseModel):
    tipo: str
    titulo: str
    ref: str | None = None


class ConsultAskOut(BaseModel):
    question: str
    answer: str
    citations: list[Citation] = []
    grounded: bool = False
    kind: str = "philosophical"
    flagged: bool = False


@router.post("/ask", response_model=ConsultAskOut)
@limiter.limit("15/hour;4/minute")
def consult_ask(
    request: Request,
    body: ConsultAskIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConsultAskOut:
    res = consult_svc.ask(db, body.question.strip())
    # Log para moderación / métricas / curación de citas.
    try:
        db.add(
            ConsultQuestion(
                user_id=user.id,
                question=res.question,
                kind=res.kind,
                grounded=res.grounded,
                flagged=res.flagged,
                answer_preview=(res.answer or "")[:500],
                citations=res.citations or None,
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    return ConsultAskOut(
        question=res.question,
        answer=res.answer,
        citations=[Citation(**c) for c in res.citations],
        grounded=res.grounded,
        kind=res.kind,
        flagged=res.flagged,
    )


_SUGGESTIONS = [
    "¿Qué es para ti la libertad?",
    "¿En qué año salió Agila?",
    "¿Qué piensas de la fama?",
    "¿De qué va de verdad «So payaso»?",
    "¿Qué es para ti la rabia?",
    "¿Por qué eres poeta antes que roquero?",
]


@router.get("/suggestions", response_model=list[str])
def consult_suggestions() -> list[str]:
    return _SUGGESTIONS
