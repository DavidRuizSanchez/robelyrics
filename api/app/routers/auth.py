"""Auth endpoints: login (JWT) + me + register + verify-email."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import EmailVerification, TermsAcceptance, User
from app.db.session import get_db
from app.services.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.services.email import EmailError, render_verify_email, send_email

router = APIRouter(prefix="/auth", tags=["auth"])

# Validador de password mínimo: 8+ chars con al menos una letra y un dígito.
_PASSWORD_OK = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")
# Validación email simple (no exhaustiva pero suficiente; la verificación real
# es enviar el correo y que el usuario clique).
_EMAIL_OK = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_VERIFY_TTL = timedelta(hours=24)


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class LoginIn(BaseModel):
    email: str
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    id: int
    email: str
    is_active: bool
    is_admin: bool
    email_verified: bool


class RegisterIn(BaseModel):
    email: str = Field(..., min_length=5, max_length=256)
    password: str = Field(..., min_length=8, max_length=128)
    accept_terms_version: str


class RegisterOut(BaseModel):
    user_id: int
    email_sent: bool


class VerifyEmailOut(BaseModel):
    ok: bool
    user_id: int
    access_token: str | None = None  # auto-login tras verificar
    token_type: str = "bearer"


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> LoginOut:
    user = (
        db.query(User)
        .filter(User.email == body.email, User.is_active.is_(True))
        .first()
    )
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad credentials")
    if user.email_verified_at is None and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="email no verificado · revisa tu bandeja de entrada",
        )
    return LoginOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        is_admin=user.is_admin,
        email_verified=user.email_verified_at is not None,
    )


@router.post("/register", response_model=RegisterOut, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterIn,
    request: Request,
    db: Session = Depends(get_db),
) -> RegisterOut:
    settings = get_settings()

    email = body.email.lower().strip()
    if not _EMAIL_OK.match(email):
        raise HTTPException(status_code=400, detail="email no válido")
    if not _PASSWORD_OK.match(body.password):
        raise HTTPException(
            status_code=400,
            detail="contraseña insegura · mínimo 8 caracteres con letras y números",
        )
    if body.accept_terms_version != settings.terms_version:
        raise HTTPException(
            status_code=400,
            detail=f"versión de términos obsoleta · vigente: {settings.terms_version}",
        )

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        # No revelamos existencia: respondemos como si todo OK pero sin reenvío.
        # Si la cuenta no estaba verificada todavía, sí re-enviamos.
        if existing.email_verified_at is None and existing.is_active:
            return _issue_and_send_verification(db, existing, settings, request)
        return RegisterOut(user_id=existing.id, email_sent=False)

    user = User(
        email=email,
        password_hash=hash_password(body.password),
        is_active=True,
        is_admin=False,
        email_verified_at=None,
    )
    db.add(user)
    db.flush()

    db.add(
        TermsAcceptance(
            user_id=user.id,
            version=body.accept_terms_version,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent", "")[:512] or None,
        )
    )

    out = _issue_and_send_verification(db, user, settings, request)
    db.commit()
    return out


@router.post("/verify-email/{token}", response_model=VerifyEmailOut)
def verify_email(token: str, db: Session = Depends(get_db)) -> VerifyEmailOut:
    row = (
        db.query(EmailVerification)
        .filter(EmailVerification.token == token)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="token no válido")
    if row.consumed_at is not None:
        raise HTTPException(status_code=400, detail="token ya consumido")
    if row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="token caducado · solicita uno nuevo")

    user = db.query(User).filter(User.id == row.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="usuario no encontrado")

    now = datetime.now(timezone.utc)
    row.consumed_at = now
    if user.email_verified_at is None:
        user.email_verified_at = now
    db.commit()

    # Auto-login tras verificar
    token_jwt = create_access_token(user.id)
    return VerifyEmailOut(ok=True, user_id=user.id, access_token=token_jwt)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _issue_and_send_verification(
    db: Session,
    user: User,
    settings,
    request: Request,
) -> RegisterOut:
    """Crea un EmailVerification y envía el correo de bienvenida."""
    token = secrets.token_urlsafe(32)
    db.add(
        EmailVerification(
            user_id=user.id,
            token=token,
            expires_at=datetime.now(timezone.utc) + _VERIFY_TTL,
        )
    )

    verify_url = f"{settings.site_url.rstrip('/')}/verificar-email/{token}"
    html, text = render_verify_email(verify_url)
    sent_id: str | None = None
    try:
        sent_id = send_email(
            to=user.email,
            subject="Confirma tu email · Entre Interiores",
            html=html,
            text=text,
        )
    except EmailError:
        # No revelamos al usuario el fallo de Resend (información sensible).
        # El log queda en stderr para el operador.
        sent_id = None

    return RegisterOut(user_id=user.id, email_sent=sent_id is not None)
