"""Auth: hash de passwords (bcrypt) + JWT (python-jose) + revocation lazy."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import RevokedToken, User
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
# bcrypt limita a 72 bytes; truncamos defensivamente para passwords largas en Unicode.
_MAX_PWD_BYTES = 72


def _to_bcrypt_bytes(plain: str) -> bytes:
    b = plain.encode("utf-8")
    return b[:_MAX_PWD_BYTES]


def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt(rounds=get_settings().bcrypt_rounds)
    return bcrypt.hashpw(_to_bcrypt_bytes(plain), salt).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bcrypt_bytes(plain), hashed.encode("ascii"))
    except Exception:  # noqa: BLE001
        return False


def create_access_token(subject: str | int) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_ttl_min)).timestamp()),
        # jti único: permite revocar este token concreto en /auth/logout
        # sin tocar JWT_SECRET ni cerrar todas las sesiones.
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algo)


def decode_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algo])
    except JWTError:
        return None


def create_admin_action_token(
    post_id: int, action: str, *, ttl_hours: int = 168
) -> str:
    """JWT firmado para que el admin pueda aprobar/rechazar un post con un
    click desde el email, sin estar logueado. TTL por defecto 7 días.

    El claim `purpose='admin_action'` lo separa de los access tokens normales
    para que no sean intercambiables.
    """
    if action not in {"approve", "reject"}:
        raise ValueError("action debe ser 'approve' o 'reject'")
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "purpose": "admin_action",
        "post_id": post_id,
        "action": action,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=ttl_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algo)


def decode_admin_action_token(token: str) -> dict[str, Any] | None:
    """Devuelve el payload solo si es un token válido de admin-action."""
    data = decode_token(token)
    if not data:
        return None
    if data.get("purpose") != "admin_action":
        return None
    if data.get("action") not in {"approve", "reject"}:
        return None
    if not isinstance(data.get("post_id"), int):
        return None
    return data


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")
    data = decode_token(token)
    if not data or "sub" not in data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    # Revocation check: el jti debe NO estar en revoked_tokens. Tokens
    # antiguos (pre-jti, emitidos antes de Ola 1.6) no llevan claim — los
    # tratamos como válidos para no romper sesiones activas; expirarán
    # naturalmente en ≤30 días.
    jti = data.get("jti")
    if jti:
        revoked = (
            db.query(RevokedToken.id).filter(RevokedToken.jti == jti).first()
        )
        if revoked:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token revoked")
    try:
        user_id = int(data["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid sub") from None
    user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    # Bulk revocation: si tras emitir el token el user reseteo password
    # (o un admin forzó cierre), tokens_invalid_before > iat → 401.
    if user.tokens_invalid_before is not None:
        iat = data.get("iat")
        if iat is not None and int(user.tokens_invalid_before.timestamp()) >= int(iat):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="session invalidated · please log in again",
            )
    return user


def revoke_all_user_tokens(db: Session, user_id: int) -> bool:
    """Cierra todas las sesiones activas del user.

    Mecanismo: actualiza users.tokens_invalid_before = now(). En el
    siguiente request, get_current_user compara payload.iat contra ese
    timestamp y rechaza si iat < tokens_invalid_before.

    Ventaja vs añadir cada jti a revoked_tokens: O(1) para "revocar todo"
    y O(1) para verificar (ya tenemos el user en el query principal).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    user.tokens_invalid_before = datetime.now(timezone.utc)
    db.commit()
    return True


def revoke_token(db: Session, token: str) -> bool:
    """Revoca un JWT añadiendo su jti a la tabla revoked_tokens. Idempotente.
    Devuelve True si se ha revocado (o ya estaba revocado), False si el
    token es inválido o no tiene jti."""
    data = decode_token(token)
    if not data:
        return False
    jti = data.get("jti")
    if not jti:
        return False
    try:
        user_id = int(data.get("sub", "0"))
    except (TypeError, ValueError):
        return False
    exp = data.get("exp")
    if not exp:
        return False
    # idempotente: si ya está, no insertamos otra fila
    if db.query(RevokedToken.id).filter(RevokedToken.jti == jti).first():
        return True
    db.add(
        RevokedToken(
            jti=jti,
            user_id=user_id,
            expires_at=datetime.fromtimestamp(int(exp), tz=timezone.utc),
        )
    )
    db.commit()
    return True


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin required")
    return user
