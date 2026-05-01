"""Crea o actualiza el usuario admin desde ADMIN_EMAIL/ADMIN_PASSWORD del entorno.

Idempotente: si el email ya existe, actualiza la pass.

Ejecución:
  docker compose exec api python -m scripts.seed_admin
"""
from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.db.models import User
from app.services.auth import hash_password
from scripts.research.common import get_session, log


def main() -> None:
    settings = get_settings()
    if not settings.admin_email or not settings.admin_password:
        log("ADMIN_EMAIL y ADMIN_PASSWORD deben estar en el entorno", "err")
        return

    pwd_hash = hash_password(settings.admin_password)

    with get_session() as db:
        stmt = (
            pg_insert(User)
            .values(
                email=settings.admin_email,
                password_hash=pwd_hash,
                is_active=True,
            )
            .on_conflict_do_update(
                index_elements=["email"],
                set_={"password_hash": pwd_hash, "is_active": True},
            )
            .returning(User.id)
        )
        user_id = db.execute(stmt).scalar_one()
        log(f"admin upserted · id={user_id} email={settings.admin_email}", "ok")


if __name__ == "__main__":
    main()
