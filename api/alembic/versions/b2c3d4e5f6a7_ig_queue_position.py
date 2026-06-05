"""Orden manual de la cola de Instagram: columna `position` en
`instagram_queue`. Se convierte en la clave primaria de orden de publicación
(menor `position` = se publica antes); `slot`/`day`/`created_at` quedan solo
como desempate. El admin la reordena arrastrando desde
/biblioteca/admin/instagram.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-05 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "instagram_queue",
        sa.Column(
            "position", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.create_index(
        "ix_instagram_queue_position", "instagram_queue", ["position"]
    )
    # Backfill: respeta el orden de publicación actual (slot, day, created_at)
    # para no alterar lo ya encolado.
    op.execute(
        """
        WITH ordered AS (
            SELECT id,
                   row_number() OVER (ORDER BY slot, day, created_at) - 1 AS rn
            FROM instagram_queue
        )
        UPDATE instagram_queue q
           SET position = o.rn
          FROM ordered o
         WHERE q.id = o.id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_instagram_queue_position", table_name="instagram_queue")
    op.drop_column("instagram_queue", "position")
