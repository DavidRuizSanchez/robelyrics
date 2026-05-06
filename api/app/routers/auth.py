"""Auth endpoints: login (JWT) + me + register + verify-email."""
from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import EmailVerification, PasswordReset, TermsAcceptance, User
from app.db.session import get_db
from app.services.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    revoke_all_user_tokens,
    revoke_token,
    verify_password,
)
from app.services.email import (
    EmailError,
    render_reset_password_email,
    render_verify_email,
    send_email,
)
from app.services.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("robelyrics.auth")

# Validador de password mínimo: 8+ chars con al menos una letra y un dígito.
_PASSWORD_OK = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")
# Validación email simple (no exhaustiva pero suficiente; la verificación real
# es enviar el correo y que el usuario clique).
_EMAIL_OK = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_VERIFY_TTL = timedelta(hours=24)
# TTL más corto para reset password: ataque típico requiere robo del email
# en una ventana — 30 min minimiza la exposición y es suficiente UX.
_RESET_TTL = timedelta(minutes=30)


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
    # Respuesta deliberadamente uniforme: no revelamos si el user ya existía
    # ni si el envío de email tuvo éxito. email_sent siempre True para impedir
    # email enumeration. Si el envío real falla, queda en logs del operador.
    email_sent: bool = True


class VerifyEmailOut(BaseModel):
    ok: bool
    user_id: int
    access_token: str | None = None  # auto-login tras verificar
    token_type: str = "bearer"


class ForgotPasswordIn(BaseModel):
    email: str = Field(..., min_length=5, max_length=256)


class ForgotPasswordOut(BaseModel):
    # Respuesta uniforme: no revelamos si el email existe.
    ok: bool = True


class ResetPasswordIn(BaseModel):
    password: str = Field(..., min_length=8, max_length=128)


class ResetPasswordOut(BaseModel):
    ok: bool
    access_token: str  # auto-login tras reset (sesión nueva, las viejas mueren)
    token_type: str = "bearer"


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@router.post("/login", response_model=LoginOut)
@limiter.limit("5/minute;20/hour")
def login(
    request: Request,
    body: LoginIn,
    db: Session = Depends(get_db),
) -> LoginOut:
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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    db: Session = Depends(get_db),
) -> None:
    """Revoca el JWT del header Authorization. El frontend tras esto
    debe borrar la cookie httpOnly. Idempotente: se puede llamar varias
    veces sin error, sin token también responde 204."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        revoke_token(db, token)
    return None


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
@limiter.limit("3/hour")
def register(
    request: Request,
    body: RegisterIn,
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

    # Respuesta uniforme: no diferenciamos los 3 casos hacia el cliente
    #   1) email nuevo                    → crear + enviar verificación
    #   2) email existente sin verificar  → re-enviar verificación
    #   3) email existente verificado     → no enviamos nada (lo reportamos en log)
    # En los 3, devolvemos RegisterOut(email_sent=True) para no filtrar
    # email enumeration por la respuesta.
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        if existing.email_verified_at is None and existing.is_active:
            _issue_and_send_verification(db, existing, settings, request)
        else:
            log.info("register: email already verified, skipping send (user_id=%s)", existing.id)
        return RegisterOut(email_sent=True)

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

    _issue_and_send_verification(db, user, settings, request)
    return RegisterOut(email_sent=True)


@router.post("/verify-email/{token}", response_model=VerifyEmailOut)
def verify_email(token: str, db: Session = Depends(get_db)) -> VerifyEmailOut:
    """Idempotente:
      - Token válido sin consumir y user no verificado → verifica + autologin.
      - Token consumido pero user verificado → autologin igual (caso típico
        cuando Outlook/Gmail Safe Links pre-fetchea el enlace).
      - Token expirado o desconocido → error.
    """
    row = (
        db.query(EmailVerification)
        .filter(EmailVerification.token == token)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="token no válido")

    user = db.query(User).filter(User.id == row.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="usuario no encontrado")

    if row.consumed_at is not None:
        # Si el token ya se usó pero el user terminó verificado, devolvemos OK
        # con autologin para que el usuario reintente sin frustración.
        if user.email_verified_at is not None:
            return VerifyEmailOut(
                ok=True,
                user_id=user.id,
                access_token=create_access_token(user.id),
            )
        raise HTTPException(status_code=400, detail="token ya consumido")

    if row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="token caducado · solicita uno nuevo")

    now = datetime.now(timezone.utc)
    row.consumed_at = now
    if user.email_verified_at is None:
        user.email_verified_at = now
    db.commit()

    return VerifyEmailOut(
        ok=True,
        user_id=user.id,
        access_token=create_access_token(user.id),
    )


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordOut,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("3/hour")
def forgot_password(
    request: Request,
    body: ForgotPasswordIn,
    db: Session = Depends(get_db),
) -> ForgotPasswordOut:
    """Inicia el flujo de reset de contraseña.

    Respuesta deliberadamente uniforme `{ok:true}` exista o no el email
    para impedir email enumeration. Si el email existe y está activo:
      1. Invalida los tokens de reset previos no consumidos del user.
      2. Crea un nuevo token con TTL de 30 min.
      3. Envía email con link a /reset-password/{token}.
    Si NO existe (o está inactivo / no verificado): no hace nada pero
    responde igual.
    """
    settings = get_settings()
    email = body.email.lower().strip()
    if not _EMAIL_OK.match(email):
        # Validación estructural: NO revela existencia, sólo formato.
        return ForgotPasswordOut(ok=True)

    user = (
        db.query(User)
        .filter(User.email == email, User.is_active.is_(True))
        .first()
    )
    if user and user.email_verified_at is not None:
        # Invalidar tokens previos pendientes de este user (single-use ↔
        # re-issue): cuando alguien pide otro reset, los antiguos ya no
        # sirven. Reduce ventana de ataque si el primer email se filtró.
        now = datetime.now(timezone.utc)
        (
            db.query(PasswordReset)
            .filter(
                PasswordReset.user_id == user.id,
                PasswordReset.consumed_at.is_(None),
                PasswordReset.expires_at > now,
            )
            .update({PasswordReset.consumed_at: now}, synchronize_session=False)
        )
        token = secrets.token_urlsafe(32)
        db.add(
            PasswordReset(
                user_id=user.id,
                token=token,
                expires_at=now + _RESET_TTL,
                request_ip=_client_ip(request),
            )
        )
        db.commit()

        reset_url = f"{settings.site_url.rstrip('/')}/reset-password/{token}"
        html, text = render_reset_password_email(reset_url)
        try:
            send_email(
                to=user.email,
                subject="Restablece tu contraseña · Entre Interiores",
                html=html,
                text=text,
            )
        except EmailError as e:
            log.warning("send reset email failed for user_id=%s: %s", user.id, e)
    else:
        log.info("forgot-password for unknown/unverified email=%s", email)

    return ForgotPasswordOut(ok=True)


@router.post(
    "/reset-password/{token}",
    response_model=ResetPasswordOut,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("10/hour")
def reset_password(
    request: Request,
    token: str,
    body: ResetPasswordIn,
    db: Session = Depends(get_db),
) -> ResetPasswordOut:
    """Consume un token de reset y cambia la contraseña.

    Tras éxito:
      1. password_hash actualizado con bcrypt nuevo.
      2. Token marcado como consumido (single-use).
      3. tokens_invalid_before = now() → revoca TODAS las sesiones JWT
         activas del user (force logout en otros dispositivos). Ataque
         típico: el atacante ya tiene un JWT robado; al cambiar password
         queremos cerrarle también ese.
      4. Nuevo JWT emitido para auto-login en el dispositivo actual.
    """
    if not _PASSWORD_OK.match(body.password):
        raise HTTPException(
            status_code=400,
            detail="contraseña insegura · mínimo 8 caracteres con letras y números",
        )

    row = (
        db.query(PasswordReset)
        .filter(PasswordReset.token == token)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="token no válido")
    if row.consumed_at is not None:
        raise HTTPException(status_code=400, detail="token ya consumido · solicita uno nuevo")
    if row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="token caducado · solicita uno nuevo")

    user = db.query(User).filter(User.id == row.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="usuario no encontrado")

    now = datetime.now(timezone.utc)
    user.password_hash = hash_password(body.password)
    row.consumed_at = now
    db.commit()

    # Cierra todas las sesiones JWT activas del user (force logout). Tras
    # esto, el commit anterior ya quedó persistido; este es lazy y O(1).
    revoke_all_user_tokens(db, user.id)

    return ResetPasswordOut(
        ok=True,
        access_token=create_access_token(user.id),
    )


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
) -> None:
    """Crea un EmailVerification, persiste, y envía el correo de bienvenida.

    El commit ocurre ANTES de send_email para garantizar que, si el correo
    llega y el usuario clica, el token existe en la BD. Si commiteamos después
    del envío y el handler revierte por cualquier excepción, el email viajaría
    con un token huérfano.

    No devuelve nada: el flujo de respuesta uniforme se gestiona en register().
    """
    token = secrets.token_urlsafe(32)
    db.add(
        EmailVerification(
            user_id=user.id,
            token=token,
            expires_at=datetime.now(timezone.utc) + _VERIFY_TTL,
        )
    )
    db.commit()

    verify_url = f"{settings.site_url.rstrip('/')}/verificar-email/{token}"
    html, text = render_verify_email(verify_url)
    try:
        send_email(
            to=user.email,
            subject="Confirma tu email · Entre Interiores",
            html=html,
            text=text,
        )
    except EmailError as e:
        # Log para el operador; la respuesta al usuario sigue siendo uniforme
        # (email_sent=True) para no filtrar email enumeration.
        log.warning("send verification email failed for user_id=%s: %s", user.id, e)
