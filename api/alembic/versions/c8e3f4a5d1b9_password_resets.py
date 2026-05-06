"""password_resets table + users.tokens_invalid_before for revoke-all on reset

Revision ID: c8e3f4a5d1b9
Revises: b7e9f1c4a2d3
Create Date: 2026-05-06 12:30:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8e3f4a5d1b9"
down_revision: str | None = "b7e9f1c4a2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Tabla de tokens de password reset
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_ip", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_password_resets_token"),
    )
    op.create_index(
        "ix_password_resets_user", "password_resets", ["user_id"]
    )
    op.create_index(
        "ix_password_resets_expires", "password_resets", ["expires_at"]
    )

    # Timestamp para invalidar todos los JWT activos del user (force logout
    # en TODO el resto de dispositivos tras un reset de password).
    # JWT con iat < users.tokens_invalid_before → 401 token revoked.
    op.add_column(
        "users",
        sa.Column(
            "tokens_invalid_before",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "tokens_invalid_before")
    op.drop_index("ix_password_resets_expires", table_name="password_resets")
    op.drop_index("ix_password_resets_user", table_name="password_resets")
    op.drop_table("password_resets")
